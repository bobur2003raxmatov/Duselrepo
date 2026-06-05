import json
import logging
import asyncio
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
            data = json.loads(request.body)
            asyncio.run(self._handle(data))
        except Exception as e:
            logger.exception(f"Webhook xato: {e}")
        return HttpResponse(status=200)

    async def _handle(self, data):
        from config import TOKEN, WEBHOOK_URL
        from bot import build_application, post_init_webhook, error_handler
        from telegram import Update
        app = build_application(webhook_mode=True, post_init_cb=post_init_webhook)
        app.add_error_handler(error_handler)
        await app.initialize()
        await app.start()
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
        await app.stop()
        await app.shutdown()

    def get(self, request, token):
        return HttpResponse("Bot ishlayapti", status=200)
