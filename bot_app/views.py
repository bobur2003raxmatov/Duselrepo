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
    try:
        future.result()
    except Exception as exc:
        logger.exception(f"[wh] process_update xato: {exc}")


@csrf_exempt
def health_view(request):
    """Hech qanday bot state ishlatmasdan darhol javob beradi."""
    return HttpResponse(f"ok pid={os.getpid()}", content_type="text/plain")


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

            # Bot hali tayyorlanmagan
            if app is None or loop is None or loop.is_closed():
                if not bot_apps._bot_thread_alive():
                    bot_apps.ensure_bot_running()
                return HttpResponse(status=503)

            # Loop o'chib qolgan — qayta ishga tushir
            if not loop.is_running():
                logger.error(f"[wh] loop ishlamayapti pid={os.getpid()} — restart")
                bot_apps.ensure_bot_running()
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
        loop      = bot_apps._loop
        loop_ok   = loop is not None and not loop.is_closed() and loop.is_running()
        pid       = os.getpid()
        if app_ready and loop_ok:
            return HttpResponse(f"Bot ishlayapti | pid={pid} | loop=ok")
        return HttpResponse(
            f"Bot tayyor emas | pid={pid} | "
            f"app={'ok' if app_ready else 'none'} | "
            f"loop={'ok' if loop_ok else 'none'}"
        )
