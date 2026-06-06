import asyncio
import json
import logging

from django.http import HttpResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


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
                logger.warning("[wh] Bot hali tayyor emas — update o'tkazib yuborildi")
                return HttpResponse(status=200)
            data = json.loads(request.body)
            uid  = data.get("update_id", "?")
            from telegram import Update
            update = Update.de_json(data, app.bot)
            asyncio.run_coroutine_threadsafe(app.process_update(update), loop)
            logger.info(f"[wh] update#{uid} → process_update")
        except Exception as e:
            logger.exception(f"[wh] Webhook xato: {e}")
        return HttpResponse(status=200)

    def get(self, request, token):
        from bot_app import apps as bot_apps
        status = "Bot ishlayapti" if bot_apps._app else "Bot tayyor emas"
        return HttpResponse(status)
