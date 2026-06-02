import json
import logging
import threading

from django.http import HttpResponse, HttpResponseForbidden
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

logger = logging.getLogger(__name__)

_bot_app   = None
_start_lock = threading.Lock()
_started    = False


def set_bot_app(app):
    global _bot_app
    _bot_app = app


def _ensure_bot_started():
    """Worker processda bot thread yo'q bo'lsa, bir marta ishga tushiradi."""
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
    from bot_app.apps import _start_bot_thread
    _start_bot_thread()
    logger.info("Bot worker processda ishga tushirildi.")


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):

    def post(self, request, token):
        from config import TOKEN as _TOKEN
        if token != _TOKEN:
            return HttpResponseForbidden("Invalid token")

        from bot_app.apps import get_bot_app, get_bot_loop
        app  = get_bot_app()
        loop = get_bot_loop()

        if app is None or loop is None:
            from bot_app.apps import _bot_thread_alive
            if not _bot_thread_alive():
                _ensure_bot_started()
            return HttpResponse(status=503)

        try:
            from telegram import Update
            data   = json.loads(request.body)
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
