import asyncio
import json
import logging
import queue
import threading

from django.http import HttpResponse, HttpResponseForbidden
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

logger = logging.getLogger(__name__)

_start_lock = threading.Lock()
_starting   = False

# Bot tayyor bo'lmaguncha kelgan xom JSON update lar
_pending: queue.Queue = queue.Queue(maxsize=500)

# views.py da ham juftlik saqlaymiz (apps.py dan sinxronlashadi)
_bot_state: tuple | None = None


def set_bot_state(app, loop):
    global _bot_state
    _bot_state = (app, loop)
    _flush_pending(app, loop)
    logger.info(f"✅ set_bot_state: pending={_pending.qsize()} ta update")


def _flush_pending(app, loop):
    count = 0
    while True:
        try:
            data = _pending.get_nowait()
        except queue.Empty:
            break
        try:
            from telegram import Update
            update = Update.de_json(data, app.bot)
            asyncio.run_coroutine_threadsafe(app.process_update(update), loop)
            count += 1
        except Exception as e:
            logger.warning(f"Pending flush xatosi: {e}")
    if count:
        logger.info(f"✅ {count} ta kutayotgan update qayta ishlandi.")


def _ensure_bot_started():
    global _starting
    from bot_app.apps import _bot_thread_alive
    if _bot_thread_alive():
        return
    with _start_lock:
        if _starting or _bot_thread_alive():
            return
        _starting = True
    try:
        from bot_app.apps import _start_bot_thread
        _start_bot_thread()
    finally:
        with _start_lock:
            _starting = False


def _patch_date(data: dict) -> dict:
    for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
        if isinstance(data.get(key), dict) and "date" not in data[key]:
            data[key]["date"] = 0
    cq = data.get("callback_query")
    if isinstance(cq, dict) and isinstance(cq.get("message"), dict):
        if "date" not in cq["message"]:
            cq["message"]["date"] = 0
    return data


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):

    def post(self, request, token):
        from config import TOKEN as _TOKEN
        if token != _TOKEN:
            return HttpResponseForbidden("Invalid token")

        try:
            data = _patch_date(json.loads(request.body))
        except Exception as e:
            logger.warning(f"Webhook JSON xatosi: {e}")
            return HttpResponse(status=200)

        from bot_app.apps import _bot_thread_alive

        if not _bot_thread_alive():
            _ensure_bot_started()

        # views._bot_state dan olish (apps._bot_state bilan sinxron)
        state = _bot_state
        if state is None:
            # apps.py dan ham tekshirish (birinchi request da race condition bo'lishi mumkin)
            from bot_app.apps import get_bot_state
            state = get_bot_state()

        uid = data.get("update_id", "?")

        if state is not None:
            app, loop = state
            try:
                from telegram import Update
                update = Update.de_json(data, app.bot)
                asyncio.run_coroutine_threadsafe(app.process_update(update), loop)
                logger.info(f"[wh] update#{uid} → process_update (pid={__import__('os').getpid()})")
            except Exception as e:
                logger.exception(f"process_update xatosi: {e}")
        else:
            logger.info(f"[wh] update#{uid} → pending (bot tayyor emas)")
            try:
                _pending.put_nowait(data)
            except queue.Full:
                logger.warning("Pending queue to'la — update tashlab yuborildi.")

        return HttpResponse(status=200)

    def get(self, request, token):
        from config import TOKEN as _TOKEN
        if token != _TOKEN:
            return HttpResponseForbidden()
        from bot_app.apps import get_bot_app
        status = "✅ Bot ishlayapti" if get_bot_app() else "⚠️ Bot tayyor emas"
        return HttpResponse(status)
