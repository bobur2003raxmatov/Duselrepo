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


def _log(msg: str) -> None:
    """Xabarni ham print (uWSGI stdout/stderr), ham logger orqali chiqaradi."""
    print(f"[bot_app] {msg}", flush=True)
    logger.warning(msg)


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
            _log(f"[postfork] pid={os.getpid()} — bot ishga tushmoqda")
            _start_bot_thread()

        _log("uWSGI postfork hook royxatdan otdi.")
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
    _log(f"Bot thread ishga tushirildi (pid={os.getpid()}).")


async def _init_bot_async(my_loop: asyncio.AbstractEventLoop):
    global _app, _loop

    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)

    from bot import build_application, post_init_webhook, error_handler
    from config import TOKEN, WEBHOOK_URL

    for attempt in range(6):
        app = None
        try:
            _log(f"[init] urinish {attempt + 1}/6  pid={os.getpid()}")

            # post_init_cb=None — biz qolda chaqiramiz (initialize() chaqirmaydi)
            app = build_application(webhook_mode=True)
            app.add_error_handler(error_handler)

            _log("[init] app.initialize() ...")
            await asyncio.wait_for(app.initialize(), timeout=60)
            _log("[init] app.initialize() OK")

            # PTB initialize() post_init'ni chaqirmaydi — qolda chaqiramiz
            _log("[init] post_init_webhook() ...")
            await asyncio.wait_for(post_init_webhook(app), timeout=30)
            _log("[init] post_init_webhook() OK")

            # APScheduler ni executor threadda ishga tushir
            # (event loop ichidan call_soon_threadsafe → deadlock oldini olish)
            if app.job_queue:
                scheduler = app.job_queue.scheduler
                scheduler._eventloop = my_loop

                _log("[init] scheduler executor threadda ishlamoqda...")
                try:
                    await asyncio.wait_for(
                        asyncio.get_running_loop().run_in_executor(None, scheduler.start),
                        timeout=15,
                    )
                    _log("[init] scheduler OK")
                except (asyncio.TimeoutError, Exception) as se:
                    _log(f"[init] scheduler xato: {se!r} — job queue ochirildi")
                    app._job_queue = None

            # app.start() orniga minimal sozlash
            app._running = True
            _log("[init] app._running = True")

            if app.persistence:
                try:
                    asyncio.create_task(app._persistence_updater())
                    _log("[init] persistence_updater yaratildi")
                except Exception as pe:
                    _log(f"[init] persistence_updater xato (ignored): {pe}")

            # Webhook URLni fon da ornating (bloklamaydi, xato bosa ignored)
            if WEBHOOK_URL:
                full_wh_url = f"{WEBHOOK_URL}/webhook/{TOKEN}/"
                asyncio.create_task(_set_webhook_safe(app, full_wh_url))

            _app  = app
            _loop = my_loop
            _log(f"[init] === BOT TAYYOR! pid={os.getpid()} ===")
            return

        except Exception as e:
            delay = 2 ** attempt
            _log(
                f"[init] XATO urinish {attempt + 1}/6: "
                f"{type(e).__name__}: {e} — {delay}s kutiladi"
            )
            if app is not None:
                try:
                    await asyncio.wait_for(app.shutdown(), timeout=5)
                except Exception:
                    pass
            await asyncio.sleep(delay)

    _log(f"[init] Bot 6 urinishdan keyin ham ishlamadi! pid={os.getpid()}")


async def _set_webhook_safe(app, url: str) -> None:
    """Webhook URLni Telegram ga ornating. Xato bosa — e'tibor berma."""
    from telegram import Update
    try:
        await asyncio.wait_for(
            app.bot.set_webhook(
                url,
                allowed_updates=list(Update.ALL_TYPES),
                drop_pending_updates=False,
            ),
            timeout=25,
        )
        _log(f"[webhook] set_webhook OK: {url}")
    except Exception as e:
        _log(f"[webhook] set_webhook xato (ignored): {type(e).__name__}: {e}")
