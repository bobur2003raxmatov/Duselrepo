import json
import logging
import queue
import threading
import time

from django.http import HttpResponse, HttpResponseForbidden
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

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


def _get_valid_state() -> tuple | None:
    """(_bot_state) ni tekshirib, loop tirik bo'lsa qaytaradi."""
    state = _bot_state
    if state is None:
        from bot_app.apps import get_bot_state
        state = get_bot_state()
    if state is None:
        return None
    app, loop = state
    if loop.is_closed():
        return None
    return state


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):

    def post(self, request, token):
        t0 = time.monotonic()

        # ── Token tekshiruv ───────────────────────────────────────
        try:
            from config import TOKEN as _TOKEN
        except Exception as e:
            logger.error(f"[wh] config import xatosi: {e}")
            return HttpResponse(status=200)

        if token != _TOKEN:
            return HttpResponseForbidden("Invalid token")

        # ── JSON parse ────────────────────────────────────────────
        try:
            data = json.loads(request.body)
            asyncio.run(self._handle(data))
        except Exception as e:
            logger.warning(f"[wh] JSON xatosi: {e}")
            return HttpResponse(status=200)

        uid = data.get("update_id", "?")
        logger.info(f"[wh] update#{uid} keldi (t={time.monotonic()-t0:.3f}s)")

        # ── Bot holati ────────────────────────────────────────────
        try:
            from bot_app.apps import _bot_thread_alive
            if not _bot_thread_alive():
                logger.info(f"[wh] update#{uid} → bot thread yo'q, ishga tushirilmoqda")
                _ensure_bot_started()

            state = _get_valid_state()

            if state is not None:
                app, loop = state
                try:
                    from telegram import Update
                    tg_update = Update.de_json(data, app.bot)
                    asyncio.run_coroutine_threadsafe(app.process_update(tg_update), loop)
                    logger.info(f"[wh] update#{uid} → process_update (t={time.monotonic()-t0:.3f}s)")
                except Exception as e:
                    logger.exception(f"[wh] update#{uid} process_update xatosi: {e}")
            else:
                logger.info(f"[wh] update#{uid} → pending (bot tayyor emas, t={time.monotonic()-t0:.3f}s)")
                try:
                    _pending.put_nowait(data)
                except queue.Full:
                    logger.warning(f"[wh] Pending queue to'la — update#{uid} tashlab yuborildi.")

        except Exception as e:
            logger.exception(f"[wh] update#{uid} kutilmagan xato: {e}")

        elapsed = time.monotonic() - t0
        logger.info(f"[wh] update#{uid} → 200 ({elapsed*1000:.1f}ms)")
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
        try:
            from config import TOKEN as _TOKEN
        except Exception:
            return HttpResponseForbidden()
        if token != _TOKEN:
            return HttpResponseForbidden()
        from bot_app.apps import get_bot_app
        status = "✅ Bot ishlayapti" if get_bot_app() else "⚠️ Bot tayyor emas"
        return HttpResponse(status)
