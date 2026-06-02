import asyncio
import json
import logging

from django.http import HttpResponse, HttpResponseForbidden
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

logger = logging.getLogger(__name__)

_bot_app = None


def set_bot_app(app):
    global _bot_app
    _bot_app = app


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
            logger.error("Bot application tayyor emas")
            return HttpResponse(status=503)

        try:
            from telegram import Update
            data   = json.loads(request.body)
            update = Update.de_json(data, app.bot)
            # Bot ning o'z event loop ida processing — bloklanmasin
            asyncio.run_coroutine_threadsafe(app.process_update(update), loop)
        except Exception as e:
            logger.exception(f"Webhook xatosi: {e}")

        return HttpResponse(status=200)

    def get(self, request, token):
        from config import TOKEN as _TOKEN
        if token != _TOKEN:
            return HttpResponseForbidden()
        app = get_bot_app() if False else _bot_app
        status = "✅ Bot ishlayapti" if app else "⚠️ Bot tayyor emas"
        return HttpResponse(status)
