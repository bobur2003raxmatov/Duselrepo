import asyncio
import logging
import os
import sys
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)

_app   = None
_loop  = None
_ready = False


def get_bot_app():
    return _app


def get_bot_loop():
    return _loop


class BotAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bot_app"
    verbose_name = "Dusel Bot"

    def ready(self):
        global _ready
        if _ready:
            return
        if not os.environ.get("TOKEN"):
            return
        argv = " ".join(sys.argv)
        skip_cmds = ("migrate", "collectstatic", "makemigrations",
                     "shell", "createsuperuser", "runbot", "bot.py")
        if any(c in argv for c in skip_cmds):
            return
        _ready = True
        _register_postfork_or_start()


def _register_postfork_or_start():
    try:
        import uwsgidecorators

        @uwsgidecorators.postfork
        def _postfork():
            if not os.environ.get("TOKEN"):
                return
            logger.info(f"[postfork] pid={os.getpid()} — bot ishga tushmoqda")
            _start_bot_thread()

        logger.info("uWSGI postfork hook ro'yxatdan o'tdi.")
    except ImportError:
        _start_bot_thread()


def _start_bot_thread():
    global _app, _loop
    _app  = None
    _loop = None
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True, name="telegram-bot")
    t.start()
    asyncio.run_coroutine_threadsafe(_init_bot_async(loop), loop)
    logger.info(f"Bot thread ishga tushirildi (pid={os.getpid()}).")


def _dbg(msg: str) -> None:
    """Logger bypass — to'g'ridan stderr ga yozadi."""
    try:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
    except Exception:
        pass


async def _init_bot_async(my_loop: asyncio.AbstractEventLoop):
    global _app, _loop

    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)

    from bot import build_application, post_init_webhook, error_handler

    for attempt in range(6):
        app = None
        try:
            _dbg(f"[init] urinish {attempt + 1}/6 pid={os.getpid()}")
            app = build_application(webhook_mode=True, post_init_cb=post_init_webhook)
            app.add_error_handler(error_handler)

            _dbg("[init] app.initialize() boshlandi")
            await asyncio.wait_for(app.initialize(), timeout=60)
            _dbg("[init] app.initialize() tugadi — app.start() background task")

            # app.start() ni background task sifatida ishga tushiramiz.
            # PTB/Python 3.13 da create_task(_update_fetcher) qatorida hang bo'ladi.
            # Webhook mode da _update_fetcher kerak emas — process_update to'g'ridan
            # chaqiriladi. Biz faqat _running=True va scheduler ishga tushishini kutamiz.
            asyncio.ensure_future(app.start())

            # _running = True app.start() boshlanishi bilan o'rnatiladi (await dan oldin).
            # Scheduler started chiqishi bilan job queue ham tayyor.
            # Shundan keyin bot webhook uchun tayyor hisoblanadi.
            deadline = asyncio.get_event_loop().time() + 10
            while not app.running:
                if asyncio.get_event_loop().time() > deadline:
                    logger.warning("app.start() 10s ichida _running o'rnatmadi — majburan davom etilmoqda")
                    app._running = True
                    break
                await asyncio.sleep(0.1)

            _dbg(f"[init] app.running={app.running} — _app o'rnatilmoqda")
            _app  = app
            _loop = my_loop
            logger.info(f"Bot tayyor (pid={os.getpid()}).")
            return

        except Exception as e:
            delay = 2 ** attempt
            logger.warning(
                f"Bot init xatosi (urinish {attempt + 1}/6): "
                f"{type(e).__name__}: {e} — {delay}s kutiladi"
            )
            _dbg(f"[init] XATO urinish {attempt + 1}: {type(e).__name__}: {e}")
            if app is not None:
                try:
                    await asyncio.wait_for(app.stop(), timeout=5)
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(app.shutdown(), timeout=5)
                except Exception:
                    pass
            await asyncio.sleep(delay)

    logger.error(f"Bot 6 urinishdan keyin ham ishga tushmadi! (pid={os.getpid()})")
    _dbg(f"[init] 6 urinish — muvaffaqiyatsiz pid={os.getpid()}")
