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
        import sys, time
        t0 = time.monotonic()
        def log(msg):
            sys.stderr.write(f"[WH {time.monotonic()-t0:.3f}s] {msg}\n")
            sys.stderr.flush()

        log("START")
        from config import TOKEN as _TOKEN
        if token != _TOKEN:
            return HttpResponseForbidden("Invalid token")

        from bot_app.apps import get_bot_app, get_bot_loop, _bot_thread_alive
        app  = get_bot_app()
        loop = get_bot_loop()
        log(f"app={app is not None} loop={loop is not None} thread={_bot_thread_alive()}")

        if app is None or loop is None:
            if not _bot_thread_alive():
                _ensure_bot_started()
            log("503")
            return HttpResponse(status=503)

        try:
            from telegram import Update
            data   = json.loads(request.body)
            log("de_json start")
            update = Update.de_json(data, app.bot)
            log("put_nowait start")
            loop.call_soon_threadsafe(app.update_queue.put_nowait, update)
            log("put_nowait done")
        except Exception as e:
            log(f"ERR {e}")
            logger.exception(f"Webhook xatosi: {e}")

        log("200")
        return HttpResponse(status=200)

    def get(self, request, token):
        from config import TOKEN as _TOKEN
        if token != _TOKEN:
            return HttpResponseForbidden()
        from bot_app.apps import get_bot_app
        status = "✅ Bot ishlayapti" if get_bot_app() else "⚠️ Bot tayyor emas"
        return HttpResponse(status)
