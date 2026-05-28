"""
So'rov (request) workflow handlers.

Agent (all 4 types) : Agent → Supervisor (approval) → Group
Supervisor / FR     : → Group directly (no approval step)
Admin               : receives NO operational requests
"""
import json
import logging
import time
from collections import defaultdict
from datetime import datetime

from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from config import (
    ADMIN_ID, GROUP_CHAT_ID,
    SOROV_TUR, SOROV_DOKON, SOROV_LOK, SOROV_TEL,
    SOROV_FOTO, SOROV_IZOH, SOROV_CONFIRM,
    SOROV_BATCH_COLLECT, SOROV_BATCH_PREVIEW,
    LIMIT_DOKON, LIMIT_SUMMA,
    INSTRUKSIYA_VIDEO_ID, BATCH_TIMEOUT_SEC,
)
from keyboards import (
    remove_kb, agent_kb, supervisor_kb, filial_rahbari_kb,
    sorov_tur_kb, sorov_tasdiqlash_kb, sorov_agent_confirm_kb,
    batch_collect_kb, batch_preview_kb,
    sorov_action_inline,
)
from telegram.helpers import escape_markdown


def _dokon_foto_id(dokon_nomi: str) -> str | None:
    """Return photo file_id if dokon_nomi is a photo marker, else None."""
    if dokon_nomi and dokon_nomi.startswith("PHOTO:"):
        return dokon_nomi[6:]
    return None


def _dokon_display(dokon_nomi: str) -> str:
    """Human-readable dokon name for card text."""
    if _dokon_foto_id(dokon_nomi):
        return "📸 Rasm yuborildi"
    return dokon_nomi

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════

def em(text) -> str:
    return escape_markdown(str(text) if text is not None else "—", version=2)


_rate_cache: dict[int, float] = defaultdict(float)
_RATE_SEC = 0.5


def _rate_limited(uid: int) -> bool:
    now = time.monotonic()
    if now - _rate_cache[uid] < _RATE_SEC:
        return True
    _rate_cache[uid] = now
    return False


def _lavozim_to_role(lavozim: str) -> str:
    return {
        "Agent":          "agent",
        "Supervisor":     "supervisor",
        "Filial Rahbari": "filial_rahbari",
        "Distribyutor":   "distribyutor",
    }.get(lavozim, (lavozim or "unknown").lower())


def _role_kb(lavozim: str):
    if lavozim == "Agent":
        return agent_kb()
    if lavozim == "Filial Rahbari":
        return filial_rahbari_kb()
    return supervisor_kb()


def _elapsed(sana_str: str) -> str:
    try:
        created = datetime.strptime(sana_str, "%Y-%m-%d %H:%M:%S")
        diff = datetime.now() - created
        total = int(diff.total_seconds())
        h, m = divmod(total // 60, 60)
        return f"{h} soat {m} daqiqa" if h else f"{m} daqiqa"
    except Exception:
        return "—"


async def _resolve_group(uid: int, lavozim: str) -> tuple:
    """Return (supervisor_id, group_chat_id) for the given user.

    Falls back to the main GROUP_CHAT_ID when no specific group is configured,
    so requests are never silently lost.
    """
    if lavozim == "Agent":
        sup_id = await db.get_biriktirish(uid)
        group  = await db.get_supervisor_group(sup_id) if sup_id else None
        return sup_id, group or GROUP_CHAT_ID
    if lavozim in ("Supervisor", "Filial Rahbari"):
        group = await db.get_supervisor_group(uid)
        return None, group or GROUP_CHAT_ID
    return None, GROUP_CHAT_ID


async def _send_media(context, chat_id: int, media_ref: str):
    """Send a stored file (format: 'type:file_id') to chat_id."""
    if not media_ref or ":" not in media_ref:
        return
    media_type, file_id = media_ref.split(":", 1)
    try:
        if media_type == "photo":
            await context.bot.send_photo(chat_id=chat_id, photo=file_id)
        elif media_type == "document":
            await context.bot.send_document(chat_id=chat_id, document=file_id)
        elif media_type == "video":
            await context.bot.send_video(chat_id=chat_id, video=file_id)
        elif media_type == "voice":
            await context.bot.send_voice(chat_id=chat_id, voice=file_id)
    except Exception as e:
        logger.warning(f"Media yuborishda xato ({media_type}): {e}")


# ══════════════════════════════════════════════
# CARD BUILDERS  (all return MarkdownV2 text)
# ══════════════════════════════════════════════

def _card_lokatsiya(ism: str, dokon: str, lat, lon, sorov_id: int, lavozim: str = "Agent") -> str:
    coords = f"`{lon:.6f}; {lat:.6f}`" if (lat is not None and lon is not None) else "—"
    return (
        f"📍 *Lokatsiya o'zgartirish*\n"
        f"👤 {em(lavozim)}: {em(ism)}\n"
        f"🏪 Dokon: {em(_dokon_display(dokon))}\n"
        f"📌 {coords}\n"
        f"🆔 So'rov \\#{sorov_id}"
    )


def _card_telefon(ism: str, dokon: str, phone: str, sorov_id: int, lavozim: str = "Agent") -> str:
    return (
        f"📞 *Raqam o'zgartirish*\n"
        f"👤 {em(lavozim)}: {em(ism)}\n"
        f"🏪 Dokon: {em(_dokon_display(dokon))}\n"
        f"📱 Raqam: `{em(phone)}`\n"
        f"🆔 So'rov \\#{sorov_id}"
    )


def _card_vizit(ism: str, izoh: str, sorov_id: int, lavozim: str = "Agent") -> str:
    return (
        f"🖼 *Vizitda muammo*\n"
        f"👤 {em(lavozim)}: {em(ism)}\n"
        f"💬 Izoh: {em(izoh)}\n"
        f"🆔 So'rov \\#{sorov_id}"
    )


def _card_boshqa(ism: str, text: str, sorov_id: int, lavozim: str = "Agent") -> str:
    content_line = f"📝 {em(text[:500])}\n" if text else ""
    return (
        f"💬 *Boshqa muammo*\n"
        f"👤 {em(lavozim)}: {em(ism)}\n"
        f"{content_line}"
        f"🆔 So'rov \\#{sorov_id}"
    )


def _card_limit(ism: str, dokon: str, limit_val: str, sorov_id: int) -> str:
    limit_lines = "\n".join(f"  • {em(line.strip())}" for line in limit_val.splitlines() if line.strip())
    return (
        f"💰 *Limit qo'shish*\n"
        f"👤 Filial Rahbari: {em(ism)}\n"
        f"🏪 Dokon: {em(dokon)}\n"
        f"💵 Yangi limitlar:\n{limit_lines}\n"
        f"🆔 So'rov \\#{sorov_id}"
    )


def _build_card(sorov: tuple, lavozim: str = "Agent") -> str:
    """Build a card from a sorovlar DB row (used in approval callback)."""
    # cols: id[0] agent_id[1] agent_ism[2] tur[3] dokon_nomi[4] yangi_qiymat[5]
    #       lat[6] lon[7] foto_ids[8] izoh[9] status[10] supervisor_id[11]
    #       sup_msg_id[12] admin_msg_id[13] sana[14] group_id[15]
    ism   = sorov[2]
    tur   = sorov[3]
    dokon = sorov[4] or "—"
    qiymat = sorov[5] or "—"
    lat, lon = sorov[6], sorov[7]
    izoh  = sorov[9] or "—"
    sid   = sorov[0]

    if tur == "lokatsiya":
        return _card_lokatsiya(ism, dokon, lat, lon, sid, lavozim)
    if tur == "telefon":
        return _card_telefon(ism, dokon, qiymat, sid, lavozim)
    if tur == "vizit":
        return _card_vizit(ism, izoh, sid, lavozim)
    if tur == "limit":
        return _card_limit(ism, dokon, qiymat, sid)
    return _card_boshqa(ism, izoh, sid, lavozim)


# ══════════════════════════════════════════════
# SEND TO SUPERVISOR (with approval buttons)
# ══════════════════════════════════════════════

async def _send_to_supervisor(context, sorov_id: int, sorov_data: dict,
                               ism: str, supervisor_id: int):
    tur     = sorov_data.get("tur", "")
    dokon   = sorov_data.get("dokon_nomi", "—")
    lavozim = sorov_data.get("lavozim", "Agent")

    if tur == "lokatsiya":
        card = _card_lokatsiya(ism, dokon, sorov_data.get("lat"), sorov_data.get("lon"), sorov_id, lavozim)
    elif tur == "telefon":
        card = _card_telefon(ism, dokon, sorov_data.get("yangi_qiymat", "—"), sorov_id, lavozim)
    elif tur == "vizit":
        card = _card_vizit(ism, sorov_data.get("izoh", "—"), sorov_id, lavozim)
        # Send photo+video to supervisor before approval card
        foto_ids  = sorov_data.get("fotolar", [])
        video_ids = sorov_data.get("videolar", [])
        all_media = (
            [InputMediaPhoto(fid) for fid in foto_ids] +
            [InputMediaVideo(fid) for fid in video_ids]
        )
        if len(all_media) == 1:
            try:
                if foto_ids:
                    await context.bot.send_photo(chat_id=supervisor_id, photo=foto_ids[0])
                else:
                    await context.bot.send_video(chat_id=supervisor_id, video=video_ids[0])
            except Exception as e:
                logger.warning(f"Vizit media supervisorga yuborishda xato: {e}")
        elif all_media:
            try:
                for chunk_start in range(0, len(all_media), 10):
                    await context.bot.send_media_group(
                        chat_id=supervisor_id, media=all_media[chunk_start:chunk_start + 10]
                    )
            except Exception as e:
                logger.warning(f"Vizit media supervisorga yuborishda xato: {e}")
    else:  # boshqa
        card = _card_boshqa(ism, sorov_data.get("izoh", ""), sorov_id, lavozim)
        media_ref = sorov_data.get("media_ref")
        if media_ref:
            await _send_media(context, supervisor_id, media_ref)

    dokon_nomi = sorov_data.get("dokon_nomi", "")
    foto_id = _dokon_foto_id(dokon_nomi)
    try:
        if foto_id:
            sent = await context.bot.send_photo(
                chat_id=supervisor_id,
                photo=foto_id,
                caption=card,
                parse_mode="MarkdownV2",
                reply_markup=sorov_tasdiqlash_kb(sorov_id),
            )
        else:
            sent = await context.bot.send_message(
                chat_id=supervisor_id,
                text=card,
                parse_mode="MarkdownV2",
                reply_markup=sorov_tasdiqlash_kb(sorov_id),
                disable_web_page_preview=True,
            )
        await db.update_sorov_sup_msg_id(sorov_id, sent.message_id)
    except Exception as e:
        logger.warning(f"Supervisor ga sorov yuborishda xato: {e}")


# ══════════════════════════════════════════════
# POST TO GROUP (final delivery, no buttons)
# ══════════════════════════════════════════════

async def _post_to_group(context, sorov_id: int, sorov_data: dict,
                          ism: str, group_chat_id: int, topic_id: int | None = None):
    tur     = sorov_data.get("tur", "")
    dokon   = sorov_data.get("dokon_nomi", "—")
    lavozim = sorov_data.get("lavozim", "Agent")
    foto_id = _dokon_foto_id(dokon)

    async def _send(thread: dict):
        if tur == "lokatsiya":
            card = _card_lokatsiya(ism, dokon, sorov_data.get("lat"), sorov_data.get("lon"), sorov_id, lavozim)
            if foto_id:
                await context.bot.send_photo(chat_id=group_chat_id, photo=foto_id,
                                             caption=card, parse_mode="MarkdownV2", **thread)
            else:
                await context.bot.send_message(chat_id=group_chat_id, text=card,
                                               parse_mode="MarkdownV2", disable_web_page_preview=True, **thread)
        elif tur == "telefon":
            card = _card_telefon(ism, dokon, sorov_data.get("yangi_qiymat", "—"), sorov_id, lavozim)
            if foto_id:
                await context.bot.send_photo(chat_id=group_chat_id, photo=foto_id,
                                             caption=card, parse_mode="MarkdownV2", **thread)
            else:
                await context.bot.send_message(chat_id=group_chat_id, text=card,
                                               parse_mode="MarkdownV2", disable_web_page_preview=True, **thread)
        elif tur == "vizit":
            caption = _card_vizit(ism, sorov_data.get("izoh", "—"), sorov_id, lavozim)
            foto_ids  = sorov_data.get("fotolar", [])
            video_ids = sorov_data.get("videolar", [])
            all_media = (
                [InputMediaPhoto(fid) for fid in foto_ids] +
                [InputMediaVideo(fid) for fid in video_ids]
            )
            if len(all_media) == 1:
                if foto_ids:
                    await context.bot.send_photo(
                        chat_id=group_chat_id, photo=foto_ids[0],
                        caption=caption, parse_mode="MarkdownV2", **thread
                    )
                else:
                    await context.bot.send_video(
                        chat_id=group_chat_id, video=video_ids[0],
                        caption=caption, parse_mode="MarkdownV2", **thread
                    )
            elif all_media:
                all_media[0] = type(all_media[0])(
                    media=all_media[0].media, caption=caption, parse_mode="MarkdownV2"
                )
                for chunk_start in range(0, len(all_media), 10):
                    await context.bot.send_media_group(
                        chat_id=group_chat_id, media=all_media[chunk_start:chunk_start + 10], **thread
                    )
            else:
                await context.bot.send_message(
                    chat_id=group_chat_id, text=caption, parse_mode="MarkdownV2", **thread
                )
        else:  # boshqa
            card = _card_boshqa(ism, sorov_data.get("izoh", ""), sorov_id, lavozim)
            await context.bot.send_message(
                chat_id=group_chat_id, text=card, parse_mode="MarkdownV2", **thread
            )
            media_ref = sorov_data.get("media_ref") or sorov_data.get("yangi_qiymat")
            if media_ref:
                await _send_media(context, group_chat_id, media_ref)

    thread = {"message_thread_id": topic_id} if topic_id else {}
    try:
        await _send(thread)
    except Exception as e:
        err_str = str(e).lower()
        if topic_id and ("thread" in err_str or "topic" in err_str or "message_thread" in err_str):
            logger.warning(f"Topic {topic_id} yopiq/yo'q, umumiy topicga qayta yubormoqda: {e}")
            await _send({})
            thread = {}
        else:
            raise

    await db.update_sorov_group_id(sorov_id, group_chat_id)
    try:
        await context.bot.send_message(
            chat_id=group_chat_id,
            text=f"⬇️ So'rov \\#{sorov_id} — amal tanlang:",
            parse_mode="MarkdownV2",
            reply_markup=sorov_action_inline(sorov_id),
            **thread,
        )
    except Exception as e:
        logger.warning(f"Sorov action footer yuborishda xato: {e}")


async def _post_to_group_from_db(context, sorov: tuple, group_chat_id: int, topic_id: int | None = None):
    """Post to group using a sorovlar DB row (used in approval callback).
    If topic_id is closed/invalid, retries without topic_id."""
    tur      = sorov[3]
    ism      = sorov[2]
    dokon    = sorov[4] or "—"
    qiymat   = sorov[5] or "—"
    lat, lon = sorov[6], sorov[7]
    izoh     = sorov[9] or "—"
    sorov_id = sorov[0]
    agent_id = sorov[1]

    agent_row = await db.get_xodim(agent_id)
    lavozim = agent_row[3] if agent_row else "Agent"
    foto_id = _dokon_foto_id(dokon)

    async def _send_card(thread: dict):
        if tur == "lokatsiya":
            card = _card_lokatsiya(ism, dokon, lat, lon, sorov_id, lavozim)
            if foto_id:
                await context.bot.send_photo(chat_id=group_chat_id, photo=foto_id,
                                             caption=card, parse_mode="MarkdownV2", **thread)
            else:
                await context.bot.send_message(chat_id=group_chat_id, text=card,
                                               parse_mode="MarkdownV2", disable_web_page_preview=True, **thread)
        elif tur == "telefon":
            card = _card_telefon(ism, dokon, qiymat, sorov_id, lavozim)
            if foto_id:
                await context.bot.send_photo(chat_id=group_chat_id, photo=foto_id,
                                             caption=card, parse_mode="MarkdownV2", **thread)
            else:
                await context.bot.send_message(chat_id=group_chat_id, text=card,
                                               parse_mode="MarkdownV2", disable_web_page_preview=True, **thread)
        elif tur == "vizit":
            caption = _card_vizit(ism, izoh, sorov_id, lavozim)
            foto_ids = json.loads(sorov[8]) if sorov[8] else []
            if len(foto_ids) == 1:
                await context.bot.send_photo(
                    chat_id=group_chat_id, photo=foto_ids[0],
                    caption=caption, parse_mode="MarkdownV2", **thread
                )
            elif foto_ids:
                all_media = [InputMediaPhoto(fid) for fid in foto_ids]
                all_media[0] = InputMediaPhoto(
                    media=all_media[0].media, caption=caption, parse_mode="MarkdownV2"
                )
                for chunk_start in range(0, len(all_media), 10):
                    await context.bot.send_media_group(
                        chat_id=group_chat_id, media=all_media[chunk_start:chunk_start + 10], **thread
                    )
            else:
                await context.bot.send_message(
                    chat_id=group_chat_id, text=caption, parse_mode="MarkdownV2", **thread
                )
        else:  # boshqa / limit
            card = _build_card(sorov, lavozim)
            await context.bot.send_message(
                chat_id=group_chat_id, text=card, parse_mode="MarkdownV2", **thread
            )
            if tur == "boshqa" and qiymat and ":" in qiymat:
                await _send_media(context, group_chat_id, qiymat)

    thread = {"message_thread_id": topic_id} if topic_id else {}
    try:
        await _send_card(thread)
    except Exception as e:
        err_str = str(e).lower()
        if topic_id and ("thread" in err_str or "topic" in err_str or "message_thread" in err_str):
            logger.warning(f"Topic {topic_id} yopiq/yo'q, umumiy topicga qayta yubormoqda: {e}")
            await _send_card({})
            thread = {}
        else:
            raise

    await db.update_sorov_group_id(sorov_id, group_chat_id)
    try:
        await context.bot.send_message(
            chat_id=group_chat_id,
            text=f"⬇️ So'rov \\#{sorov_id} — amal tanlang:",
            parse_mode="MarkdownV2",
            reply_markup=sorov_action_inline(sorov_id),
            **thread,
        )
    except Exception as e:
        logger.warning(f"Sorov action footer yuborishda xato: {e}")


# ══════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════

async def sorov_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if _rate_limited(uid):
        return ConversationHandler.END
    user = await db.get_xodim(uid)
    if not user or user[0] != "approved":
        return ConversationHandler.END

    lavozim = user[3]
    context.user_data["sorov_data"] = {"agent_ism": user[2], "lavozim": lavozim}

    if lavozim == "Supervisor":
        return await _enter_batch_mode(update, context)

    # Agent / Filial Rahbari — all 4 types
    await update.message.reply_text(
        "❓ *Savol turini tanlang:*",
        parse_mode="Markdown",
        reply_markup=sorov_tur_kb(),
    )
    return SOROV_TUR


# ══════════════════════════════════════════════
# TYPE SELECTION
# ══════════════════════════════════════════════

async def sorov_tur_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tur = query.data[len("sorov_tur_"):]  # lokatsiya | telefon | vizit | boshqa

    context.user_data["sorov_data"]["tur"] = tur

    if tur in ("lokatsiya", "telefon"):
        await query.edit_message_text(
            "🏪 *Dokon nomini yoki kodini yozing:*",
            parse_mode="Markdown",
        )
        return SOROV_DOKON

    if tur == "vizit":
        await query.edit_message_text(
            "🖼 *Vizitda muammo*\n\nKamida 3 ta rasm yuboring "
            "(do'kon nomi va vizitda qo'shilgan bo'limlar ko'rinsin):",
            parse_mode="Markdown",
        )
        context.user_data["sorov_data"]["fotolar"] = []
        return SOROV_FOTO

    # boshqa → batch mode
    await query.edit_message_text("💬 *Boshqa muammo*", parse_mode="Markdown")
    return await _enter_batch_mode(update, context)


# ══════════════════════════════════════════════
# STORE NAME
# ══════════════════════════════════════════════

async def sorov_dokon_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _rate_limited(update.effective_user.id):
        return SOROV_DOKON
    context.user_data["sorov_data"]["dokon_nomi"] = update.message.text.strip()
    return await _sorov_dokon_next(update, context)


async def sorov_dokon_foto_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]  # eng yuqori sifatli
    context.user_data["sorov_data"]["dokon_nomi"] = f"PHOTO:{photo.file_id}"
    return await _sorov_dokon_next(update, context)


async def _sorov_dokon_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tur = context.user_data["sorov_data"]["tur"]

    if tur == "lokatsiya":
        await update.message.reply_text(
            "📍 *Dokon yangi lokatsiyasini yuboring:*\n"
            "_Faqat Telegram lokatsiya (GPS) qabul qilinadi._",
            parse_mode="Markdown",
        )
        return SOROV_LOK

    await update.message.reply_text(
        "📞 *Yangi raqamni yozing:*\n"
        "_Masalan: 901234567 yoki +998901234567_",
        parse_mode="Markdown",
    )
    return SOROV_TEL


# ══════════════════════════════════════════════
# LOCATION (GPS only)
# ══════════════════════════════════════════════

async def sorov_lok_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.location:
        await update.message.reply_text(
            "❌ Faqat Telegram lokatsiya qabul qilinadi.\n"
            "📎 Qo'shimcha → Lokatsiya tugmasini bosing."
        )
        return SOROV_LOK

    loc = update.message.location
    context.user_data["sorov_data"]["lat"] = loc.latitude
    context.user_data["sorov_data"]["lon"] = loc.longitude
    return await _show_agent_preview(update, context)


# ══════════════════════════════════════════════
# PHONE (auto-formatted)
# ══════════════════════════════════════════════

def _format_phone(raw: str) -> str | None:
    digits = "".join(filter(str.isdigit, raw))
    if not digits:
        return None
    if digits.startswith("998"):
        digits = digits[3:]
    elif digits.startswith("8") and len(digits) == 10:
        digits = digits[1:]
    elif digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 9:
        return None
    return f"+998{digits}"


async def sorov_tel_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        await update.message.reply_text(
            "❌ Telefon raqamini yozing:\n_Masalan: 901234567_",
            parse_mode="Markdown",
        )
        return SOROV_TEL
    phone = _format_phone(update.message.text.strip())
    if not phone:
        await update.message.reply_text(
            "❌ Noto'g'ri raqam. Quyidagilardan birini kiriting:\n"
            "• 901234567\n• 0901234567\n• 998901234567\n• +998901234567\n\nQayta kiriting:"
        )
        return SOROV_TEL
    context.user_data["sorov_data"]["yangi_qiymat"] = phone
    return await _show_agent_preview(update, context)


# ══════════════════════════════════════════════
# PHOTOS (collect ≥3)
# ══════════════════════════════════════════════

async def sorov_foto_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ Iltimos, rasm yuboring.")
        return SOROV_FOTO

    fotolar = context.user_data["sorov_data"].setdefault("fotolar", [])
    fotolar.append(update.message.photo[-1].file_id)
    count = len(fotolar)

    if count < 3:
        remaining = 3 - count
        await update.message.reply_text(
            f"✅ {count} ta rasm qabul qilindi. Yana {remaining} ta yuboring."
        )
        return SOROV_FOTO

    # Exactly at 3 → prompt for description. Extra photos (media group) silently accepted.
    if count == 3:
        await update.message.reply_text(
            f"✅ {count} ta rasm qabul qilindi!\n\n"
            "📝 *Muammo haqida batafsil izoh yozing:*",
            parse_mode="Markdown",
        )
        return SOROV_IZOH

    # count > 3: extra photo from media group, just store silently
    return SOROV_FOTO


# ══════════════════════════════════════════════
# DESCRIPTION (vizit)
# ══════════════════════════════════════════════

async def sorov_izoh_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sorov_data"]["izoh"] = update.message.text.strip()
    return await _show_agent_preview(update, context)


# ══════════════════════════════════════════════
# BATCH MODE — collect, preview, submit
# ══════════════════════════════════════════════

def _cancel_batch_timer(context: ContextTypes.DEFAULT_TYPE, uid: int) -> None:
    for job in context.job_queue.get_jobs_by_name(f"batch_{uid}"):
        job.schedule_removal()


def _reschedule_batch_timer(context: ContextTypes.DEFAULT_TYPE, uid: int) -> None:
    _cancel_batch_timer(context, uid)
    context.job_queue.run_once(
        _batch_auto_submit_job,
        when=BATCH_TIMEOUT_SEC,
        data={"uid": uid},
        name=f"batch_{uid}",
        chat_id=uid,
        user_id=uid,
    )


async def _batch_auto_submit_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Auto-submits batch after 3 minutes of inactivity."""
    uid: int = context.job.data["uid"]
    user_data = context.application.user_data.get(uid, {})
    batch = user_data.get("batch", {})
    sorov_data = user_data.get("sorov_data", {})

    total = sum(len(batch.get(k, [])) for k in ("messages", "photos", "files", "voices", "videos"))
    if total == 0:
        return

    lavozim = sorov_data.get("lavozim", "Agent")
    sorov_id = await _do_submit_batch(uid, user_data, context)

    try:
        if sorov_id:
            sent = await context.bot.send_message(
                chat_id=uid,
                text=(
                    f"⏱ *3 daqiqa o'tdi\\.* \\#{sorov_id}\\-so'rovingiz avtomatik yuborildi\\!"
                ),
                parse_mode="MarkdownV2",
                reply_markup=_role_kb(lavozim),
            )
            await db.update_sorov_agent_msg_id(sorov_id, sent.message_id)
        else:
            await context.bot.send_message(
                chat_id=uid,
                text="⚠️ Avtomatik yuborishda xato\\. Admin bilan bog'laning\\.",
                parse_mode="MarkdownV2",
                reply_markup=_role_kb(lavozim),
            )
    except Exception as e:
        logger.warning(f"Auto-submit bildirishnomasi yuborishda xato: {e}")

    user_data.pop("batch", None)
    user_data.pop("sorov_data", None)


async def _enter_batch_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    context.user_data["batch"] = {
        "messages": [], "photos": [], "files": [], "voices": [], "videos": []
    }
    _reschedule_batch_timer(context, uid)
    await context.bot.send_message(
        chat_id=uid,
        text=(
            "📩 *Muammo yozish rejimi*\n\n"
            "Xabar, rasm yoki fayl yuboring\\.\n"
            "Tayyor bo'lgach *'📤 Yuborish'* tugmasini bosing\\.\n"
            "⏱ _3 daqiqa faolsiz bo'lsangiz, avtomatik yuboriladi\\._"
        ),
        parse_mode="MarkdownV2",
        reply_markup=batch_collect_kb(),
    )
    return SOROV_BATCH_COLLECT


async def batch_collect_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Accepts all incoming content in collection mode."""
    msg = update.message
    uid = update.effective_user.id
    if _rate_limited(uid):
        return SOROV_BATCH_COLLECT

    if msg.text and msg.text.strip() == "📤 Yuborish":
        return await _show_batch_preview(update, context)

    batch = context.user_data.setdefault("batch", {
        "messages": [], "photos": [], "files": [], "voices": [], "videos": []
    })

    text = (msg.text or msg.caption or "").strip()
    if text:
        batch["messages"].append(text)
    if msg.photo:
        batch["photos"].append(msg.photo[-1].file_id)
    if msg.document:
        batch["files"].append({"file_id": msg.document.file_id, "name": msg.document.file_name or "fayl"})
    if msg.voice:
        batch["voices"].append(msg.voice.file_id)
    if msg.video:
        batch["videos"].append(msg.video.file_id)

    _reschedule_batch_timer(context, uid)

    counts = []
    if batch["messages"]: counts.append(f"💬 {len(batch['messages'])}")
    if batch["photos"]:   counts.append(f"🖼 {len(batch['photos'])}")
    if batch["files"]:    counts.append(f"📎 {len(batch['files'])}")
    if batch["voices"]:   counts.append(f"🎙 {len(batch['voices'])}")
    if batch["videos"]:   counts.append(f"🎥 {len(batch['videos'])}")

    await msg.reply_text(
        f"✅ Qabul qilindi \\({', '.join(counts) or '0'}\\)\n"
        f"_Tayyor bo'lgach '📤 Yuborish' bosing\\._",
        parse_mode="MarkdownV2",
        reply_markup=batch_collect_kb(),
    )
    return SOROV_BATCH_COLLECT


async def _show_batch_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    batch = context.user_data.get("batch", {})
    messages = batch.get("messages", [])
    photos   = batch.get("photos", [])
    files    = batch.get("files", [])
    voices   = batch.get("voices", [])
    videos   = batch.get("videos", [])

    total = len(messages) + len(photos) + len(files) + len(voices) + len(videos)
    if total == 0:
        await update.message.reply_text(
            "❌ Hali hech narsa yuborilmagan\\. Xabar, rasm yoki fayl yuboring\\.",
            parse_mode="MarkdownV2",
            reply_markup=batch_collect_kb(),
        )
        return SOROV_BATCH_COLLECT

    text = "📋 *Yuborish oldidan tekshiring:*\n\n"
    if messages: text += f"💬 Xabarlar: *{len(messages)}* ta\n"
    if photos:   text += f"🖼 Rasmlar: *{len(photos)}* ta\n"
    if files:    text += f"📎 Fayllar: *{len(files)}* ta\n"
    if voices:   text += f"🎙 Ovozli: *{len(voices)}* ta\n"
    if videos:   text += f"🎥 Video: *{len(videos)}* ta\n"

    if messages:
        text += "\n"
        for m in messages[:3]:
            short = m[:150] + ("..." if len(m) > 150 else "")
            text += f"\n💬 _{em(short)}_"
        if len(messages) > 3:
            text += f"\n_\\.\\.\\. va yana {len(messages) - 3} ta xabar_"

    await update.message.reply_text(
        text,
        parse_mode="MarkdownV2",
        reply_markup=batch_preview_kb(),
    )
    return SOROV_BATCH_PREVIEW


async def batch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles confirm / edit / cancel from preview screen."""
    query = update.callback_query
    await query.answer()
    uid    = query.from_user.id
    action = query.data
    data   = context.user_data.get("sorov_data", {})
    lavozim = data.get("lavozim", "Agent")

    if action == "batch_confirm":
        await query.edit_message_text("⏳ Yuborilmoqda\\.\\.\\.", parse_mode="MarkdownV2")
        sorov_id = await _do_submit_batch(uid, context.user_data, context)
        _cancel_batch_timer(context, uid)
        context.user_data.pop("batch", None)
        context.user_data.pop("sorov_data", None)
        if sorov_id:
            reply_text = f"✅ *\\#{sorov_id}\\-so'rovingiz* qabul qilindi\\! ⏳ _Supervisor tasdig'ini kutmoqda\\._"
            await query.edit_message_text(reply_text, parse_mode="MarkdownV2")
            try:
                await db.update_sorov_agent_msg_id(sorov_id, query.message.message_id)
            except Exception:
                pass
        else:
            await query.edit_message_text("❌ Guruh belgilanmagan\\. Admin bilan bog'laning\\.", parse_mode="MarkdownV2")
        try:
            await context.bot.send_message(chat_id=uid, text=".", reply_markup=_role_kb(lavozim))
        except Exception:
            pass
        return ConversationHandler.END

    if action == "batch_edit":
        await query.edit_message_text("✏️ Davom eting\\, yana xabar yoki rasm yuboring\\.", parse_mode="MarkdownV2")
        await context.bot.send_message(chat_id=uid, text="📝 Yana qo'shing:", reply_markup=batch_collect_kb())
        _reschedule_batch_timer(context, uid)
        return SOROV_BATCH_COLLECT

    if action == "batch_cancel":
        _cancel_batch_timer(context, uid)
        context.user_data.pop("batch", None)
        context.user_data.pop("sorov_data", None)
        await query.edit_message_text("❌ Bekor qilindi\\.", parse_mode="MarkdownV2")
        try:
            await context.bot.send_message(chat_id=uid, text="Bosh menyu:", reply_markup=_role_kb(lavozim))
        except Exception:
            pass
        return ConversationHandler.END

    return SOROV_BATCH_PREVIEW


async def _do_submit_batch(uid: int, user_data: dict, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Core submission logic shared by manual confirm and auto-timer."""
    batch     = user_data.get("batch", {})
    sorov_data = user_data.get("sorov_data", {})

    messages = batch.get("messages", [])
    photos   = batch.get("photos", [])
    files    = batch.get("files", [])
    voices   = batch.get("voices", [])
    videos   = batch.get("videos", [])
    ism      = sorov_data.get("agent_ism", "")
    lavozim  = sorov_data.get("lavozim", "")

    combined_text = "\n".join(messages)
    all_media_json = json.dumps({"files": files, "voices": voices, "videos": videos}) if (files or voices or videos) else None

    supervisor_id, group_chat_id = await _resolve_group(uid, lavozim)

    sorov_id = await db.insert_sorov(
        agent_id=uid, agent_ism=ism, tur="boshqa",
        dokon_nomi=None, yangi_qiymat=all_media_json,
        lat=None, lon=None,
        foto_ids=json.dumps(photos) if photos else None,
        izoh=combined_text,
        supervisor_id=supervisor_id,
    )

    # Build card
    now_str = datetime.now().strftime("%d\\.%m\\.%Y %H:%M")
    role_label = em(lavozim) if lavozim else "Agent"
    card_lines = [
        f"💬 *Boshqa muammo*",
        f"👤 {role_label}: {em(ism)}",
        f"🕐 {now_str}",
    ]
    if messages:
        card_lines.append("\n📝 *Xabarlar:*")
        for m in messages:
            card_lines.append(em(m[:500]))
    card_lines.append(f"\n🆔 So'rov \\#{sorov_id}")
    card = "\n".join(card_lines)

    async def _send_photos_and_media(chat_id: int, thread_kwargs: dict = {}) -> None:
        media_group = (
            [InputMediaPhoto(fid) for fid in photos] +
            [InputMediaVideo(fid) for fid in videos]
        )
        if len(media_group) == 1:
            # Bitta media: to'g'ridan yuborish
            try:
                if photos:
                    await context.bot.send_photo(chat_id=chat_id, photo=photos[0], **thread_kwargs)
                else:
                    await context.bot.send_video(chat_id=chat_id, video=videos[0], **thread_kwargs)
            except Exception as e:
                logger.warning(f"Media yuborishda xato: {e}")
        elif media_group:
            for chunk_start in range(0, len(media_group), 10):
                try:
                    await context.bot.send_media_group(
                        chat_id=chat_id,
                        media=media_group[chunk_start:chunk_start + 10],
                        **thread_kwargs,
                    )
                except Exception as e:
                    logger.warning(f"Media group yuborishda xato: {e}")
        # Fayllar va ovozlar alohida
        for f_info in files:
            fid = f_info["file_id"] if isinstance(f_info, dict) else f_info
            try:
                await context.bot.send_document(chat_id=chat_id, document=fid, **thread_kwargs)
            except Exception as e:
                logger.warning(f"Fayl yuborishda xato: {e}")
        for fid in voices:
            try:
                await context.bot.send_voice(chat_id=chat_id, voice=fid, **thread_kwargs)
            except Exception as e:
                logger.warning(f"Ovoz yuborishda xato: {e}")

    user_row_batch = await db.get_xodim(uid)
    batch_topic_id = user_row_batch[1] if user_row_batch else None
    thread_b = {"message_thread_id": batch_topic_id} if batch_topic_id else {}

    sent_ok = False
    try:
        if lavozim == "Agent" and supervisor_id:
            sent = await context.bot.send_message(
                chat_id=supervisor_id, text=card,
                parse_mode="MarkdownV2",
                reply_markup=sorov_tasdiqlash_kb(sorov_id),
            )
            await db.update_sorov_sup_msg_id(sorov_id, sent.message_id)
            await _send_photos_and_media(supervisor_id)
            sent_ok = True
        elif group_chat_id:
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=card, parse_mode="MarkdownV2", **thread_b)
            await _send_photos_and_media(GROUP_CHAT_ID, thread_b)
            await db.update_sorov_group_id(sorov_id, GROUP_CHAT_ID)
            try:
                await context.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=f"⬇️ So'rov \\#{sorov_id} — amal tanlang:",
                    parse_mode="MarkdownV2",
                    reply_markup=sorov_action_inline(sorov_id),
                    **thread_b,
                )
            except Exception:
                pass
            sent_ok = True
    except Exception as e:
        logger.error(f"Batch yuborishda xato (uid={uid}): {e}")

    # Audit log
    try:
        await db.insert_audit_log(
            user_id=uid,
            user_role=_lavozim_to_role(lavozim),
            action_type="boshqa_muammo",
            target=None,
            old_value=None,
            new_value=combined_text[:500] if combined_text else None,
            status="pending" if lavozim == "Agent" and supervisor_id else "approved",
            request_id=sorov_id,
        )
    except Exception as _e:
        logger.warning(f"Audit log yozishda xato (batch): {_e}")

    return sorov_id if sent_ok else None


# ══════════════════════════════════════════════
# PREVIEW  — agent confirms before sending
# ══════════════════════════════════════════════

async def _show_agent_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show agent a preview of their sorov data and ask for confirmation."""
    uid = update.effective_user.id
    data = context.user_data.get("sorov_data", {})
    tur = data.get("tur", "")
    ism = data.get("agent_ism", "")
    dokon = _dokon_display(data.get("dokon_nomi", "") or "")

    if tur == "lokatsiya":
        lat = data.get("lat")
        lon = data.get("lon")
        coords = f"`{lon:.6f}; {lat:.6f}`" if (lat is not None and lon is not None) else "—"
        caption = (
            f"📍 *Lokatsiya o'zgartirish — tasdiqlash*\n\n"
            f"👤 Agent: {em(ism)}\n"
            f"🏪 Do'kon: {em(dokon)}\n"
            f"📌 {coords}\n\n"
            "_Yuqoridagi ma'lumotlar to'g'rimi?_"
        )
        await update.message.reply_text(caption, parse_mode="MarkdownV2", reply_markup=sorov_agent_confirm_kb())
        if lat is not None and lon is not None:
            await context.bot.send_location(chat_id=uid, latitude=lat, longitude=lon)

    elif tur == "telefon":
        phone = em(data.get("yangi_qiymat", "—"))
        caption = (
            f"📞 *Telefon o'zgartirish — tasdiqlash*\n\n"
            f"👤 Agent: {em(ism)}\n"
            f"🏪 Do'kon: {em(dokon)}\n"
            f"📱 Yangi raqam: {phone}\n\n"
            "_Yuqoridagi ma'lumotlar to'g'rimi?_"
        )
        await update.message.reply_text(caption, parse_mode="MarkdownV2", reply_markup=sorov_agent_confirm_kb())

    elif tur == "vizit":
        fotolar = data.get("fotolar", [])
        izoh = data.get("izoh", "—")
        caption = (
            f"🖼 *Vizit muammosi — tasdiqlash*\n\n"
            f"👤 Agent: {em(ism)}\n"
            f"📝 Izoh: {em(izoh)}\n\n"
            "_Yuqoridagi ma'lumotlar to'g'rimi?_"
        )
        if len(fotolar) >= 2:
            media = [InputMediaPhoto(fid) for fid in fotolar[:10]]
            media[0] = InputMediaPhoto(fotolar[0], caption=caption, parse_mode="MarkdownV2")
            await context.bot.send_media_group(chat_id=uid, media=media)
            await context.bot.send_message(
                chat_id=uid,
                text="✅ Yuqoridagi rasmlar va ma'lumotlar to'g'rimi?",
                reply_markup=sorov_agent_confirm_kb(),
            )
        elif len(fotolar) == 1:
            await context.bot.send_photo(chat_id=uid, photo=fotolar[0], caption=caption,
                                          parse_mode="MarkdownV2")
            await context.bot.send_message(
                chat_id=uid,
                text="✅ Yuqoridagi rasm va ma'lumotlar to'g'rimi?",
                reply_markup=sorov_agent_confirm_kb(),
            )
        else:
            await update.message.reply_text(caption, parse_mode="MarkdownV2",
                                             reply_markup=sorov_agent_confirm_kb())

    else:  # boshqa — handled by batch flow, shouldn't reach here
        await _finish_sorov(update, context)
        return ConversationHandler.END

    return SOROV_CONFIRM


async def sorov_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Agent taps ✅ Tasdiqlash or ❌ Bekor qilish on preview."""
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    action = query.data  # sorov_confirm_ok | sorov_confirm_cancel

    # Remove confirm buttons regardless
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if action == "sorov_confirm_cancel":
        context.user_data.pop("sorov_data", None)
        lavozim = (await db.get_xodim(uid) or [None, None, None, "Agent"])[3]
        await query.message.reply_text("❌ So'rov bekor qilindi.", reply_markup=_role_kb(lavozim))
        return ConversationHandler.END

    # OK — submit
    await _finish_sorov(update, context)
    return ConversationHandler.END


# ══════════════════════════════════════════════
# FINISH  (lokatsiya / telefon / vizit)
# Agent   → Supervisor for approval
# FR      → Group directly
# ══════════════════════════════════════════════

async def _finish_sorov(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = context.user_data.get("sorov_data", {})
    ism = data.get("agent_ism", "")
    lavozim = data.get("lavozim", "")
    tur = data.get("tur", "")

    foto_ids_json = json.dumps(data.get("fotolar", [])) if data.get("fotolar") else None
    supervisor_id, group_chat_id = await _resolve_group(uid, lavozim)

    sorov_id = await db.insert_sorov(
        agent_id=uid,
        agent_ism=ism,
        tur=tur,
        dokon_nomi=data.get("dokon_nomi"),
        yangi_qiymat=data.get("yangi_qiymat"),
        lat=data.get("lat"),
        lon=data.get("lon"),
        foto_ids=foto_ids_json,
        izoh=data.get("izoh"),
        supervisor_id=supervisor_id,
    )

    # ── Audit log ────────────────────────────────────────────────
    _TUR_ACTION = {
        "lokatsiya": "lokatsiya_ozgartirish",
        "telefon":   "raqam_ozgartirish",
        "vizit":     "vizit_muammo",
        "boshqa":    "boshqa_muammo",
    }
    _new_val = (
        f"{data.get('lat')}, {data.get('lon')}" if tur == "lokatsiya"
        else data.get("yangi_qiymat") if tur == "telefon"
        else (data.get("izoh") or "")[:500]
    )
    try:
        await db.insert_audit_log(
            user_id=uid,
            user_role=_lavozim_to_role(lavozim),
            action_type=_TUR_ACTION.get(tur, tur),
            target=data.get("dokon_nomi") or "—",
            old_value=None,
            new_value=_new_val,
            status="pending" if lavozim == "Agent" and supervisor_id else "approved",
            request_id=sorov_id,
        )
    except Exception as _e:
        logger.warning(f"Audit log yozishda xato (_finish_sorov): {_e}")
    # ─────────────────────────────────────────────────────────────

    user_row = await db.get_xodim(uid)
    agent_topic_id = user_row[1] if user_row else None

    sent_ok = False
    if lavozim == "Agent":
        if supervisor_id:
            await _send_to_supervisor(context, sorov_id, data, ism, supervisor_id)
            sent_ok = True
        else:
            await _post_to_group(context, sorov_id, data, ism, GROUP_CHAT_ID, agent_topic_id)
            sent_ok = True
    else:  # FR, Supervisor
        await _post_to_group(context, sorov_id, data, ism, GROUP_CHAT_ID, agent_topic_id)
        sent_ok = True

    if sent_ok:
        try:
            sent_msg = await context.bot.send_message(
                chat_id=uid,
                text=(
                    f"✅ *\\#{sorov_id}\\-so'rovingiz qabul qilindi\\!*\n"
                    f"⏳ _Supervisor tasdig'ini kutmoqda\\._"
                ),
                parse_mode="MarkdownV2",
                reply_markup=_role_kb(lavozim),
            )
            await db.update_sorov_agent_msg_id(sorov_id, sent_msg.message_id)
        except Exception as _e:
            logger.warning(f"Agent confirm msg yuborishda xato: {_e}")
    else:
        await update.message.reply_text(
            "❌ Guruh belgilanmagan. Admin bilan bog'laning.",
            reply_markup=_role_kb(lavozim),
        )
    context.user_data.pop("sorov_data", None)


# ══════════════════════════════════════════════
# SUPERVISOR APPROVE / REJECT CALLBACK
# ✅ → post card to supervisor's group
# ❌ → notify agent
# ══════════════════════════════════════════════

async def sorov_sup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, sorov_id_str = query.data.rsplit("_", 1)
    sorov_id = int(sorov_id_str)

    sorov = await db.get_sorov(sorov_id)
    if not sorov:
        await query.edit_message_text("❌ So'rov topilmadi.")
        return

    # cols: id[0] agent_id[1] agent_ism[2] tur[3] dokon_nomi[4] yangi_qiymat[5]
    #       lat[6] lon[7] foto_ids[8] izoh[9] status[10] supervisor_id[11]
    #       sup_msg_id[12] admin_msg_id[13] sana[14] group_id[15]
    agent_id  = sorov[1]
    tur       = sorov[3]
    dokon     = sorov[4] or "—"
    sana      = sorov[14]
    sup_uid   = update.effective_user.id

    sup_row = await db.get_xodim(sup_uid)
    sup_role = _lavozim_to_role(sup_row[3]) if sup_row else "supervisor"

    agent_msg_id = sorov[16] if len(sorov) > 16 else None

    if action == "sorov_done":
        await db.update_sorov_status(sorov_id, "done")
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.reply_text(
            f"✅ So'rov \\#{sorov_id} bajarildi\\!",
            parse_mode="MarkdownV2",
        )
        try:
            await context.bot.send_message(
                chat_id=agent_id,
                text=f"✅ Sizning *\\#{sorov_id}\\-so'rovingiz* bajarildi\\!",
                parse_mode="MarkdownV2",
                reply_to_message_id=agent_msg_id,
            )
        except Exception:
            pass
        return

    if action == "sorov_rad":
        await db.update_sorov_status(sorov_id, "admin_rejected")
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.reply_text(
            f"❌ So'rov \\#{sorov_id} rad etildi\\.",
            parse_mode="MarkdownV2",
        )
        try:
            await context.bot.send_message(
                chat_id=agent_id,
                text=f"❌ Sizning *\\#{sorov_id}\\-so'rovingiz* rad etildi\\.",
                parse_mode="MarkdownV2",
                reply_to_message_id=agent_msg_id,
            )
        except Exception:
            pass
        return

    if action == "sorov_appr":
        try:
            await db.update_sorov_status(sorov_id, "approved")
        except Exception as _e:
            logger.error(f"[APPR] DB status update xato: {_e}")
            await query.edit_message_text("❌ DB xato. Admin bilan bog'laning.")
            return

        try:
            await db.insert_audit_log(
                user_id=sup_uid,
                user_role=sup_role,
                action_type="supervisor_tasdiqlash",
                target=dokon,
                old_value=None,
                new_value=None,
                status="approved",
                request_id=sorov_id,
            )
        except Exception as _e:
            logger.warning(f"Audit log yozishda xato (sorov_appr): {_e}")

        group_chat_id = await db.get_supervisor_group(sup_uid) or GROUP_CHAT_ID
        logger.info(f"[APPR] sorov_id={sorov_id} sup_uid={sup_uid} group_chat_id={group_chat_id}")

        agent_row_for_topic = await db.get_xodim(agent_id)
        agent_topic_id = agent_row_for_topic[1] if agent_row_for_topic else None
        if group_chat_id:
            try:
                await _post_to_group_from_db(context, sorov, GROUP_CHAT_ID, agent_topic_id)
                await query.edit_message_text(
                    f"✅ So'rov #{sorov_id} tasdiqlandi.\n"
                    f"📤 Guruhga yuborildi: `{group_chat_id}`",
                    parse_mode="Markdown",
                )
            except Exception as e:
                err = str(e)
                logger.error(f"[APPR] Guruhga yuborishda xato group={group_chat_id}: {err}")
                await query.edit_message_text(
                    f"✅ So'rov #{sorov_id} tasdiqlandi.\n"
                    f"⚠️ Guruhga yuborishda xato: {err}\n"
                    f"Group ID: `{group_chat_id}`",
                    parse_mode="Markdown",
                )
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"⚠️ Guruhga yuborishda xato\\!\n"
                             f"So'rov: \\#{sorov_id}\n"
                             f"Group: `{group_chat_id}`\n"
                             f"Xato: {em(err)}",
                        parse_mode="MarkdownV2",
                    )
                except Exception:
                    pass
        else:
            logger.error(f"[APPR] GROUP_CHAT_ID fallback also missing — sup_uid={sup_uid}")
            await query.edit_message_text(
                f"✅ So'rov #{sorov_id} tasdiqlandi.\n"
                f"⚠️ Guruhga yuborib bo'lmadi. Admin bilan bog'laning.",
                parse_mode="Markdown",
            )

        elapsed = _elapsed(sana)
        agent_msg_id = sorov[16] if len(sorov) > 16 else None
        try:
            await context.bot.send_message(
                chat_id=agent_id,
                text=(
                    f"✅ Sizning *\\#{sorov_id}\\-raqamli so'rovingiz* "
                    f"supervisor tomonidan tasdiqlandi\\!\n⏱ Vaqt: {elapsed}"
                ),
                parse_mode="MarkdownV2",
                reply_to_message_id=agent_msg_id,
            )
        except Exception:
            pass

    else:  # sorov_rej
        await db.update_sorov_status(sorov_id, "rejected")

        try:
            await db.insert_audit_log(
                user_id=sup_uid,
                user_role=sup_role,
                action_type="supervisor_rad",
                target=dokon,
                old_value=None,
                new_value=None,
                status="rejected",
                request_id=sorov_id,
            )
        except Exception as _e:
            logger.warning(f"Audit log yozishda xato (sorov_rej): {_e}")

        await query.edit_message_text(f"❌ So'rov #{sorov_id} rad etildi.")
        elapsed = _elapsed(sana)
        agent_msg_id = sorov[16] if len(sorov) > 16 else None
        try:
            await context.bot.send_message(
                chat_id=agent_id,
                text=(
                    f"❌ Sizning *\\#{sorov_id}\\-raqamli so'rovingiz* "
                    f"supervisor tomonidan rad etildi\\.\n"
                    f"🏪 Dokon: {em(dokon)}\n"
                    f"⏱ Vaqt: {elapsed}"
                ),
                parse_mode="MarkdownV2",
                reply_to_message_id=agent_msg_id,
            )
        except Exception:
            pass


# ══════════════════════════════════════════════
# LIMIT QO'SHISH (Filial Rahbari)
# FR submits → directly to FR's group (no admin step)
# ══════════════════════════════════════════════

async def limit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if _rate_limited(uid):
        return ConversationHandler.END
    user = await db.get_xodim(uid)
    if not user or user[0] != "approved" or user[3] != "Filial Rahbari":
        return ConversationHandler.END

    context.user_data["limit_data"] = {"ism": user[2]}
    await update.message.reply_text(
        "🏪 *Limit qo'shish*\n\nDokon nomini yoki kodini yozing:",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    return LIMIT_DOKON


async def limit_dokon_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["limit_data"]["dokon_nomi"] = update.message.text.strip()
    await update.message.reply_text(
        "💰 Yangi limitni yozing:\n\n"
        "_Masalan: Dusel: 1000000_",
        parse_mode="Markdown",
    )
    return LIMIT_SUMMA


async def limit_summa_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    limit_str = update.message.text.strip()
    if not limit_str:
        await update.message.reply_text("❌ Bo'sh xabar. Qayta kiriting:")
        return LIMIT_SUMMA

    data  = context.user_data.get("limit_data", {})
    dokon = data.get("dokon_nomi", "—")
    ism   = data.get("ism", "—")
    uid   = update.effective_user.id

    sorov_id = await db.insert_sorov(
        agent_id=uid, agent_ism=ism, tur="limit",
        dokon_nomi=dokon, yangi_qiymat=limit_str,
        lat=None, lon=None, foto_ids=None, izoh=None,
        supervisor_id=None,
    )

    try:
        await db.insert_audit_log(
            user_id=uid,
            user_role="filial_rahbari",
            action_type="limit_qoshish",
            target=dokon,
            old_value=None,
            new_value=limit_str,
            status="approved",
            request_id=sorov_id,
        )
    except Exception as _e:
        logger.warning(f"Audit log yozishda xato (limit): {_e}")

    user_row_lim = await db.get_xodim(uid)
    lim_topic_id = user_row_lim[1] if user_row_lim else None
    thread_l = {"message_thread_id": lim_topic_id} if lim_topic_id else {}
    card = _card_limit(ism, dokon, limit_str, sorov_id)

    try:
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=card,
            parse_mode="MarkdownV2",
            **thread_l,
        )
        await db.update_sorov_group_id(sorov_id, GROUP_CHAT_ID)
        try:
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"⬇️ So'rov \\#{sorov_id} — amal tanlang:",
                parse_mode="MarkdownV2",
                reply_markup=sorov_action_inline(sorov_id),
                **thread_l,
            )
        except Exception:
            pass
        await update.message.reply_text(
            f"✅ Limit so'rovi yuborildi!\n🏪 Dokon: {dokon}\n💰 Limitlar:\n"
            + "\n".join(f"  • {line.strip()}" for line in limit_str.splitlines()),
            reply_markup=filial_rahbari_kb(),
        )
    except Exception as e:
        logger.warning(f"Limit guruhga yuborishda xato: {e}")
        await update.message.reply_text(
            f"⚠️ Guruhga yuborishda xato: {e}",
            reply_markup=filial_rahbari_kb(),
        )

    context.user_data.pop("limit_data", None)
    return ConversationHandler.END


# ══════════════════════════════════════════════
# /instruksiya
# ══════════════════════════════════════════════

async def handle_admin_sorov_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Admin xodim so'roviga javob berganda agentga yo'naltiradi. True qaytarsa — ishlov berildi."""
    msg = update.message
    if not msg or not msg.reply_to_message:
        return False
    sorov = await db.get_sorov_by_admin_msg_id(msg.reply_to_message.message_id)
    if not sorov:
        return False
    agent_id = sorov[1]
    try:
        await context.bot.copy_message(
            chat_id=agent_id,
            from_chat_id=msg.chat_id,
            message_id=msg.message_id,
        )
    except Exception as e:
        logger.warning(f"Admin sorov javobini agentga yuborishda xato: {e}")
    return True


async def instruksiya_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = (
        "📖 *Botdan foydalanish yo'riqnomasi*\n\n"
        "• Ro'yxatdan o'tish: /start\n"
        "• Yangi klient qo'shish: 🏪 Yangi Klient\n"
        "• So'rov yuborish: ❓ So'rov\n"
        "• Bekor qilish: /cancel"
    )
    if INSTRUKSIYA_VIDEO_ID:
        await update.message.reply_video(
            video=INSTRUKSIYA_VIDEO_ID,
            caption=caption,
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            caption + "\n\n_Yo'riqnoma videosi tez orada qo'shiladi._",
            parse_mode="Markdown",
        )
