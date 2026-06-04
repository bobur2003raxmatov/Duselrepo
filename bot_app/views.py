import json
import logging
import queue
import threading

from django.http import HttpResponse, HttpResponseForbidden
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

logger = logging.getLogger(__name__)

_bot_app    = None
_start_lock = threading.Lock()
_starting   = False

# Bot tayyor bo'lmaguncha kelgan update lar — JSON dict sifatida
_pending: queue.Queue = queue.Queue(maxsize=200)


def set_bot_app(app):
    global _bot_app
    _bot_app = app
    # Bot tayyor bo'lgandan keyin navbatdagi update larni yuborish
    _flush_pending(app)


def _flush_pending(app):
    from bot_app.apps import get_bot_loop
    loop = get_bot_loop()
    if loop is None:
        return
    count = 0
    while True:
        try:
            data = _pending.get_nowait()
        except queue.Empty:
            break
        try:
            from telegram import Update
            update = Update.de_json(data, app.bot)
            loop.call_soon_threadsafe(app.update_queue.put_nowait, update)
            count += 1
        except Exception as e:
            logger.warning(f"Pending update xatosi: {e}")
    if count:
        logger.info(f"✅ {count} ta kutayotgan update bot ga yuborildi.")


def _ensure_bot_started():
    """Bot thread o'lgan bo'lsa qayta ishga tushiradi."""
    global _starting
    from bot_app.apps import _bot_thread_alive
    if _bot_thread_alive():
        return
    with _start_lock:
        if _starting or _bot_thread_alive():
            return
        _starting = True
    try:
        from bot_app.apps import _start_bot_thread
        _start_bot_thread()
    finally:
        with _start_lock:
            _starting = False


def _patch_date(data: dict) -> dict:
    """PTB 22.x: ba'zi xabarlarda 'date' maydoni yo'q."""
    for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
        if isinstance(data.get(key), dict) and "date" not in data[key]:
            data[key]["date"] = 0
    cq = data.get("callback_query")
    if isinstance(cq, dict) and isinstance(cq.get("message"), dict):
        if "date" not in cq["message"]:
            cq["message"]["date"] = 0
    return data


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):

    def post(self, request, token):
        from config import TOKEN as _TOKEN
        if token != _TOKEN:
            return HttpResponseForbidden("Invalid token")

        # Har doim 200 qaytaramiz — Telegram qayta yubormaslik uchun
        try:
            data = _patch_date(json.loads(request.body))
        except Exception as e:
            logger.warning(f"Webhook JSON xatosi: {e}")
            return HttpResponse(status=200)

        from bot_app.apps import get_bot_app, get_bot_loop, _bot_thread_alive

        if not _bot_thread_alive():
            _ensure_bot_started()

        app  = get_bot_app()
        loop = get_bot_loop()

        if app is not None and loop is not None:
            try:
                from telegram import Update
                update = Update.de_json(data, app.bot)
                loop.call_soon_threadsafe(app.update_queue.put_nowait, update)
            except Exception as e:
                logger.exception(f"Update yuborishda xato: {e}")
        else:
            # Bot hali tayyor emas — navbatga qo'yamiz
            try:
                _pending.put_nowait(data)
            except queue.Full:
                logger.warning("Pending queue to'la — update tashlab yuborildi.")

        return HttpResponse(status=200)

    def get(self, request, token):
        from config import TOKEN as _TOKEN
        if token != _TOKEN:
            return HttpResponseForbidden()
        from bot_app.apps import get_bot_app
        status = "✅ Bot ishlayapti" if get_bot_app() else "⚠️ Bot tayyor emas"
        return HttpResponse(status)
