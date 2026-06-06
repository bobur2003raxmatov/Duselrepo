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
            app = build_application(webhook_mode=True, post_init_cb=post_init_webhook)
            app.add_error_handler(error_handler)

            await asyncio.wait_for(app.initialize(), timeout=40)
            await asyncio.wait_for(app.start(), timeout=20)

            if WEBHOOK_URL:
                wh_url = f"{WEBHOOK_URL.rstrip('/')}/webhook/{TOKEN}/"
                try:
                    await asyncio.wait_for(
                        app.bot.set_webhook(url=wh_url, drop_pending_updates=False),
                        timeout=20,
                    )
                    logger.info(f"Webhook o'rnatildi: {wh_url}")
                except asyncio.TimeoutError:
                    logger.warning("set_webhook timeout — keyingi urinishda qayta harakat qilinadi")
                except Exception as e:
                    logger.warning(f"set_webhook: {e}")
            else:
                logger.warning("WEBHOOK_URL yo'q — webhook o'rnatilmadi.")

            _app  = app
            _loop = my_loop
            logger.info(f"Bot tayyor (pid={os.getpid()}).")
            return

        except (asyncio.TimeoutError, Exception) as e:
            delay = 2 ** attempt
            logger.warning(f"Bot init xatosi (urinish {attempt + 1}/6): {e} — {delay}s kutiladi")
            if app is not None:
                try:
                    await app.stop()
                    await app.shutdown()
                except Exception:
                    pass
            await asyncio.sleep(delay)

    logger.error(f"Bot 6 urinishdan keyin ham ishga tushmadi! (pid={os.getpid()})")
