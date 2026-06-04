import json
import logging
import threading

from django.http import HttpResponse, HttpResponseForbidden
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

logger = logging.getLogger(__name__)

_bot_app    = None
_start_lock = threading.Lock()
_starting   = False   # postfork yoki ensure orqali allaqachon start qilinganmi


def set_bot_app(app):
    global _bot_app
    _bot_app = app


def _ensure_bot_started():
    """Bot thread o'lgan bo'lsa qayta ishga tushiradi (postfork fallback)."""
    global _starting
    from bot_app.apps import _bot_thread_alive
    if _bot_thread_alive():
        return
    with _start_lock:
        if _starting:
            return
        if _bot_thread_alive():
            return
        _starting = True
    try:
        from bot_app.apps import _start_bot_thread
        _start_bot_thread()
        logger.info("Bot thread _ensure orqali qayta ishga tushirildi.")
    finally:
        with _start_lock:
            _starting = False


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):

    def post(self, request, token):
        from config import TOKEN as _TOKEN
        if token != _TOKEN:
            return HttpResponseForbidden("Invalid token")

        from bot_app.apps import get_bot_app, get_bot_loop, _bot_thread_alive
        import time

        # Bot thread o'lgan bo'lsa qayta ishga tushir
        if not _bot_thread_alive():
            _ensure_bot_started()

        # Bot tayyor bo'lguncha 20 soniya kutamiz (proxy retry 3x = ~9s)
        app = loop = None
        for _ in range(200):
            app  = get_bot_app()
            loop = get_bot_loop()
            if app is not None and loop is not None:
                break
            time.sleep(0.1)

        if app is None or loop is None:
            logger.warning("Bot 20s ichida tayyor bo'lmadi — 503")
            return HttpResponse(status=503)

        try:
            from telegram import Update
            data = json.loads(request.body)
            # PTB 22.x: ba'zi xabarlarda 'date' maydoni yo'q bo'ladi
            for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
                if isinstance(data.get(key), dict) and "date" not in data[key]:
                    data[key]["date"] = 0
            cq = data.get("callback_query")
            if isinstance(cq, dict) and isinstance(cq.get("message"), dict):
                if "date" not in cq["message"]:
                    cq["message"]["date"] = 0
            update = Update.de_json(data, app.bot)
            loop.call_soon_threadsafe(app.update_queue.put_nowait, update)
        except Exception as e:
            logger.exception(f"Webhook xatosi: {e}")

        return HttpResponse(status=200)

    def get(self, request, token):
        from config import TOKEN as _TOKEN
        if token != _TOKEN:
            return HttpResponseForbidden()
        from bot_app.apps import get_bot_app
        status = "✅ Bot ishlayapti" if get_bot_app() else "⚠️ Bot tayyor emas"
        return HttpResponse(status)
