import asyncio
import logging
import os
import sys
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)

_bot_app  = None
_bot_loop = None
_ready    = False


def get_bot_app():
    return _bot_app


def get_bot_loop():
    return _bot_loop


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
        _start_bot_thread()


def _start_bot_thread():
    global _bot_loop
    _bot_loop = asyncio.new_event_loop()
    t = threading.Thread(target=_bot_loop.run_forever, daemon=True, name="telegram-bot")
    t.start()
    asyncio.run_coroutine_threadsafe(_init_bot_async(), _bot_loop)
    logger.info("Bot thread ishga tushirildi (background).")


async def _init_bot_async():
    global _bot_app

    try:
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)

        from bot import build_application, post_init, error_handler
        from config import TOKEN, WEBHOOK_URL

        app = build_application(webhook_mode=True, post_init_cb=post_init)
        app.add_error_handler(error_handler)

        await app.initialize()
        await app.start()

        if WEBHOOK_URL:
            wh_url = f"{WEBHOOK_URL.rstrip('/')}/webhook/{TOKEN}/"
            await app.bot.set_webhook(url=wh_url, drop_pending_updates=True)
            logger.info(f"✅ Webhook o'rnatildi: {wh_url}")
        else:
            logger.warning("⚠️  WEBHOOK_URL yo'q — lokal testda ngrok ishlatilsin.")

        _bot_app = app
        from bot_app.views import set_bot_app
        set_bot_app(app)
        logger.info("✅ Bot webhook rejimda tayyor.")

    except Exception:
        logger.exception("❌ Bot ishga tushirishda xato!")
