import asyncio
import json
import logging
import os

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


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):

    def post(self, request, token):
        from config import TOKEN
        if token != TOKEN:
            return HttpResponse(status=403)
        try:
            from bot_app import apps as bot_apps
            app  = bot_apps._app
            loop = bot_apps._loop
            if app is None or loop is None or loop.is_closed():
                # 503 — Telegram qayta urinadi (200 bossa "yetkazildi" deb hisoblaydi)
                return HttpResponse(status=503)
            data   = json.loads(request.body)
            from telegram import Update
            update = Update.de_json(data, app.bot)
            future = asyncio.run_coroutine_threadsafe(app.process_update(update), loop)
            future.add_done_callback(_log_future_exception)
        except Exception as e:
            logger.exception(f"[wh] Webhook xato: {e}")
        return HttpResponse(status=200)

    def get(self, request, token):
        from bot_app import apps as bot_apps
        app_ready = bot_apps._app is not None
        loop_ok   = bot_apps._loop is not None and not bot_apps._loop.is_closed()
        pid       = os.getpid()
        status = (
            f"Bot ishlayapti | pid={pid}" if app_ready
            else f"Bot tayyor emas | pid={pid} | loop={'ok' if loop_ok else 'none'}"
        )
        return HttpResponse(status)
