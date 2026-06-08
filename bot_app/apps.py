import asyncio
import logging
import os
import sys
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)

_app          = None
_loop         = None
_ready        = False
_restart_lock = threading.Lock()


def _log(msg: str) -> None:
    print(f"[bot_app] {msg}", flush=True)
    logger.warning(msg)


def get_bot_app():
    return _app


def get_bot_loop():
    return _loop


def _bot_thread_alive() -> bool:
    return any(t.name == "telegram-bot" and t.is_alive() for t in threading.enumerate())


def ensure_bot_running() -> bool:
    """Fork dan keyin yoki loop o'lib qolsa bot threadni qayta ishga tushiradi."""
    current_loop = _loop
    if current_loop is not None and current_loop.is_running():
        return _app is not None
    if _bot_thread_alive():
        return False
    with _restart_lock:
        if _bot_thread_alive():
            return False
        _log(f"[ensure] bot thread yo'q — qayta ishga tushirilmoqda pid={os.getpid()}")
        _start_bot_thread()
    return False


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
            try:
                if not os.environ.get("TOKEN"):
                    return
                _log(f"[postfork] pid={os.getpid()} — bot thread boshlanmoqda")
                _start_bot_thread()
            except Exception as exc:
                _log(f"[postfork] XATO (ignored): {exc!r}")

        _log("uWSGI postfork hook ro'yxatdan o'tdi.")
    except ImportError:
        try:
            _start_bot_thread()
        except Exception as exc:
            _log(f"[start_bot_thread] XATO (ignored): {exc!r}")


def _start_bot_thread():
    """Bot daemon threadini ishga tushiradi. Hech qanday bloklovchi amal yo'q."""
    global _app, _loop
    _app  = None
    _loop = None

    def _thread_main():
        # BARCHA asyncio amallari shu daemon thread ichida — asosiy threadni bloklamaydi
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # loop.run_forever() boshlanishidan oldin init coroutineni queue ga qo'shamiz
            loop.call_soon(lambda: loop.create_task(_init_bot_async(loop)))
            loop.run_forever()
        except Exception as exc:
            _log(f"[bot-thread] FATAL: {exc!r}")

    t = threading.Thread(target=_thread_main, daemon=True, name="telegram-bot")
    t.start()
    _log(f"Bot thread ishga tushirildi (pid={os.getpid()}).")
    # MUHIM: hech qanday sleep yo'q — darhol qaytadi


async def _init_bot_async(my_loop: asyncio.AbstractEventLoop):
    global _app, _loop

    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)

    from bot import build_application, post_init_webhook, error_handler
    from config import TOKEN, WEBHOOK_URL

    for attempt in range(6):
        app = None
        started = False
        try:
            _log(f"[init] urinish {attempt + 1}/6  pid={os.getpid()}")

            app = build_application(webhook_mode=True)
            app.add_error_handler(error_handler)

            _log("[init] app.initialize() ...")
            await asyncio.wait_for(app.initialize(), timeout=60)
            _log("[init] app.initialize() OK")

            _log("[init] post_init_webhook() ...")
            await asyncio.wait_for(post_init_webhook(app), timeout=30)
            _log("[init] post_init_webhook() OK")

            _log("[init] app.start() ...")
            await asyncio.wait_for(app.start(), timeout=30)
            started = True
            _log("[init] app.start() OK — job queue va update processor ishlamoqda")

            if WEBHOOK_URL:
                full_wh_url = f"{WEBHOOK_URL}/webhook/{TOKEN}/"
                asyncio.create_task(_set_webhook_safe(app, full_wh_url))

            _app  = app
            _loop = my_loop
            _log(f"[init] === BOT TAYYOR! pid={os.getpid()} ===")
            return

        except Exception as e:
            delay = 2 ** attempt
            _log(f"[init] XATO {attempt + 1}/6: {type(e).__name__}: {e} — {delay}s kutiladi")
            if app is not None:
                try:
                    if started:
                        await asyncio.wait_for(app.stop(), timeout=5)
                    await asyncio.wait_for(app.shutdown(), timeout=5)
                except Exception:
                    pass
            await asyncio.sleep(delay)

    _log(f"[init] Bot 6 urinishdan keyin ham ishlamadi! pid={os.getpid()}")


async def _set_webhook_safe(app, url: str) -> None:
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
