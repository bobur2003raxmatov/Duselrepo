import asyncio
import logging
import os
import sys
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)

_bot_app  = None
_bot_loop = None


def _bot_thread_alive() -> bool:
    return any(
        t.name == "telegram-bot" and t.is_alive()
        for t in threading.enumerate()
    )


def get_bot_app():
    if not _bot_thread_alive():
        return None
    return _bot_app


def get_bot_loop():
    if not _bot_thread_alive():
        return None
    return _bot_loop


class BotAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bot_app"
    verbose_name = "Dusel Bot"

    def ready(self):
        if not os.environ.get("TOKEN"):
            return
        argv = " ".join(sys.argv)
        skip_cmds = ("migrate", "collectstatic", "makemigrations",
                     "shell", "createsuperuser", "runbot", "bot.py")
        if any(c in argv for c in skip_cmds):
            return
        _register_postfork_or_start()


def _register_postfork_or_start():
    """uWSGI ostida postfork hook ishlatadi; aks holda to'g'ridan-to'g'ri ishga tushiradi.

    uWSGI eager-loading rejimida apps.ready() MASTER processda (pid=1) chaqiriladi.
    Workerlar fork qilganda thread lar yo'qoladi. postfork hook har bir workerda
    fork dan KEYIN chaqiriladi — thread har workerda to'g'ri ishga tushadi.
    """
    try:
        import uwsgidecorators

        @uwsgidecorators.postfork
        def _postfork():
            if not os.environ.get("TOKEN"):
                return
            logger.info(f"[postfork] Worker pid={os.getpid()} — bot thread ishga tushmoqda.")
            _start_bot_thread()

        logger.info("✅ uWSGI postfork hook ro'yxatdan o'tdi.")

    except ImportError:
        # uWSGI yo'q (local dev yoki manage.py), to'g'ridan-to'g'ri ishga tushirish
        logger.info("uWSGI yo'q — bot to'g'ridan-to'g'ri ishga tushirilmoqda.")
        _start_bot_thread()


def _start_bot_thread():
    global _bot_loop, _bot_app
    _bot_app = None  # Fork dan keyin eski qiymatni tozalash
    _bot_loop = asyncio.new_event_loop()
    t = threading.Thread(
        target=_bot_loop.run_forever, daemon=True, name="telegram-bot"
    )
    t.start()
    asyncio.run_coroutine_threadsafe(_init_bot_async(), _bot_loop)
    logger.info(f"Bot thread ishga tushirildi (pid={os.getpid()}).")


async def _init_bot_async():
    global _bot_app

    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)

    from bot import build_application, post_init_webhook, error_handler
    from config import TOKEN, WEBHOOK_URL

    # Proxy 503 yoki tarmoq xatosi uchun exponential backoff bilan qayta urinish
    for attempt in range(6):
        try:
            app = build_application(webhook_mode=True, post_init_cb=post_init_webhook)
            app.add_error_handler(error_handler)

            await app.initialize()
            await app.start()

            if WEBHOOK_URL:
                wh_url = f"{WEBHOOK_URL.rstrip('/')}/webhook/{TOKEN}/"
                try:
                    info = await app.bot.get_webhook_info()
                    if info.url != wh_url:
                        await app.bot.set_webhook(url=wh_url, drop_pending_updates=True)
                        logger.info(f"✅ Webhook o'rnatildi: {wh_url}")
                    else:
                        logger.info(f"✅ Webhook allaqachon to'g'ri: {wh_url}")
                except Exception as e:
                    logger.warning(f"⚠️  set_webhook: {e}")
            else:
                logger.warning("⚠️  WEBHOOK_URL yo'q.")

            _bot_app = app
            from bot_app.views import set_bot_app
            set_bot_app(app)
            logger.info(f"✅ Bot tayyor (pid={os.getpid()}).")
            return

        except Exception as e:
            delay = 2 ** attempt  # 1, 2, 4, 8, 16, 32 soniya
            logger.warning(
                f"⚠️  Bot init xatosi (urinish {attempt + 1}/6): {e} — {delay}s kutiladi"
            )
            await asyncio.sleep(delay)

    logger.error(f"❌ Bot 6 urinishdan keyin ham ishga tushmadi! (pid={os.getpid()})")
