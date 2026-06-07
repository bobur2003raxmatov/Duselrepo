import asyncio
import json
import logging
import os
import time

from django.http import HttpResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


def _log_future_exception(future) -> None:
    """process_update dan kelgan yashirin xatolarni logga yozadi."""
    try:
        future.result()
    except Exception as exc:
        logger.exception(f"[wh] process_update exception: {exc}")


@csrf_exempt
def health_view(request):
    """Har qanday holatda tezda javob beradi — uWSGI/Django sog'ligini tekshirish."""
    return HttpResponse(f"ok pid={os.getpid()}", content_type="text/plain")


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):

    def post(self, request, token):
        from config import TOKEN
        if token != TOKEN:
            return HttpResponse(status=403)
        t0 = time.monotonic()
        try:
            from bot_app import apps as bot_apps
            app  = bot_apps._app
            loop = bot_apps._loop
            if app is None or loop is None or loop.is_closed():
                logger.warning(f"[wh] bot tayyor emas — 503 (dt={time.monotonic()-t0:.3f}s)")
                return HttpResponse(status=503)
            if not loop.is_running():
                logger.error("[wh] bot loop ishlamayapti — restart va 503")
                from bot_app.apps import ensure_bot_running
                ensure_bot_running()
                return HttpResponse(status=503)
            data   = json.loads(request.body)
            from telegram import Update
            update = Update.de_json(data, app.bot)
            future = asyncio.run_coroutine_threadsafe(app.process_update(update), loop)
            future.add_done_callback(_log_future_exception)
            logger.debug(f"[wh] update dispatched dt={time.monotonic()-t0:.3f}s")
        except Exception as e:
            logger.exception(f"[wh] Webhook xato: {e}")
        return HttpResponse(status=200)

    def get(self, request, token):
        from bot_app import apps as bot_apps
        app_ready  = bot_apps._app is not None
        loop       = bot_apps._loop
        loop_ok    = loop is not None and not loop.is_closed() and loop.is_running()
        pid        = os.getpid()
        status = (
            f"Bot ishlayapti | pid={pid} | loop=ok"
            if app_ready and loop_ok
            else f"Bot tayyor emas | pid={pid} | app={'ok' if app_ready else 'none'} | loop={'ok' if loop_ok else 'none'}"
        )
        return HttpResponse(status)
