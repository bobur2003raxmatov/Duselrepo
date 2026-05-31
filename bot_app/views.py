import json
import logging

from django.http import HttpResponse, HttpResponseForbidden
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

logger = logging.getLogger(__name__)

# Global PTB Application instance (populated by runbot command or startup)
_bot_app = None


def set_bot_app(app):
    global _bot_app
    _bot_app = app


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):
    async def post(self, request, token):
        from config import TOKEN
        if token != TOKEN:
            return HttpResponseForbidden("Invalid token")

        if _bot_app is None:
            logger.error("Bot application not initialized")
            return HttpResponse(status=503)

        try:
            from telegram import Update
            data = json.loads(request.body)
            update = Update.de_json(data, _bot_app.bot)
            await _bot_app.process_update(update)
        except Exception as e:
            logger.exception(f"Webhook xatosi: {e}")

        return HttpResponse(status=200)

    async def get(self, request, token):
        from config import TOKEN
        if token != TOKEN:
            return HttpResponseForbidden()
        return HttpResponse("Bot ishlayapti ✅")
