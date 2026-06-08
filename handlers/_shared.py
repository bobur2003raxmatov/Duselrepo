"""
handlers/_shared.py — Umumiy yordamchi funksiyalar va dekoratorlar.
Barcha handler fayllari shu moduldan import qiladi.
"""
import logging
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from functools import wraps

from telegram import (
    Update, ReplyParameters,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, InputMediaVideo,
    BotCommand,
)
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler
from telegram.helpers import escape_markdown

import database as db
from keyboards import (
    lavozim_kb, filial_kb, telefon_kb, telefon2_kb, remove_kb,
    admin_kb, edit_field_kb, xodimlar_page_inline, xodimlar_edit_page_inline,
    sorov_inline, bajarildi_inline, tasdiq_inline, unblock_inline,
    group_sorov_inline, group_bajarildi_inline, group_detail_back_inline,
    search_results_kb, xodim_profil_kb,
    biriktirish_list_kb, biriktir_detail_kb,
    biriktirish_agents_kb, biriktirish_checkers_kb, checker_sorov_kb,
    urgency_kb,
    pending_xodimlar_inline, blocked_xodimlar_inline,
    klient_dokon_turi_kb, klient_confirm_kb,
    klient_lokatsiya_inline_kb, klient_kategoriya_kb,
    klient_chastota_kb, klient_edit_fields_kb,
    klientlar_search_page_inline,
    mening_klientlar_kb,
    agent_kb, supervisor_kb, filial_rahbari_kb,
    operator_kb, distribyutor_kb,
    instruksiya_lavozim_kb, instruksiya_mavjud_kb,
)
from utils import (
    is_topic_valid, check_sla_timeout, generate_excel, generate_klientlar_excel, generate_full_excel,
    urgency_timeout_job, checker_timeout_job,
)
from config import (
    ADMIN_ID, GROUP_CHAT_ID, FILIALLAR, LAVOZIMLAR,
    SLA_TIMEOUT_SEC, GROUP_TIMEOUT_SEC, PAGE_SIZE,
    URGENCY_TIMEOUT_SEC, CHECKER_TIMEOUT_SEC,
    ISM, LAVOZIM, KOD, FILIAL, TELEFON, TELEFON2, TUGILGAN_KUN,
    EDIT_FIELD, EDIT_VALUE, SEARCH_QUERY,
    BIRIKTIR_AGENT, BIRIKTIR_CHECKER, BIRIKTIR_DETAIL,
    BIRIKTIR_EDIT_VALUE,
    DOKON_TURLARI, DOKON_SLUGLARI, AGENT_PREFIX_REGIONS, AGENT_DATABASE,
    KLIENT_RASM, KLIENT_FIRMA_NOMI, KLIENT_TELEFON1, KLIENT_TELEFON2,
    KLIENT_INN, KLIENT_ORIENTER, KLIENT_LOKATSIYA, KLIENT_KATEGORIYA,
    KLIENT_DOKON_TURI, KLIENT_DISTRIBUTOR, KLIENT_AGENT_KOD,
    KLIENT_LIMIT, KLIENT_CONFIRM, KLIENT_EDIT_FIELD, KLIENT_EDIT_VALUE,
    KLIENT_CHASTOTA,
    KLIENT_EDIT_LABELS,
    INSTR_MATN, ADD_ADMIN_ID,
)

logger = logging.getLogger(__name__)


# ── Dinamik role keyboard ─────────────────────────────────────────────────────
def _role_keyboard(lavozim: str):
    """DB keshi bo'lsa undan, aks holda hardcoded keyboard qaytaradi."""
    from handlers.menu_dispatch import get_kb_rows
    rows = get_kb_rows(lavozim)
    if rows:
        return ReplyKeyboardMarkup(rows, resize_keyboard=True)
    # hardcoded fallback
    if lavozim == "Agent":          return agent_kb()
    if lavozim == "Filial Rahbari": return filial_rahbari_kb()
    if lavozim == "Operator":       return operator_kb()
    if lavozim == "Distribyutor":   return distribyutor_kb()
    return supervisor_kb()


# ── Tezlik cheklovi — spam va flood dan himoya ──────────────────
# Bir foydalanuvchi 0.5 soniya ichida ikki xabar yubora olmaydi.
_last_msg_time: dict[int, float] = defaultdict(float)
_RATE_SEC = 0.5


def rate_limited(uid: int) -> bool:
    """True qaytarsa — bu xabarni e'tiborsiz qoldirish kerak."""
    now = time.monotonic()
    if now - _last_msg_time[uid] < _RATE_SEC:
        return True
    _last_msg_time[uid] = now
    return False


def _msg_ctype(msg) -> str:
    if msg.photo:      return "📷 Rasm"
    if msg.video:      return "🎥 Video"
    if msg.voice:      return "🎙 Ovoz"
    if msg.video_note: return "⭕ Video-xabar"
    if msg.document:   return "📄 Fayl"
    if msg.audio:      return "🎵 Audio"
    if msg.sticker:    return "🎭 Sticker"
    if msg.location:   return "📍 Lokatsiya"
    if msg.contact:    return "📱 Kontakt"
    if msg.text:       return "💬 Matn"
    return "💬 Xabar"


def em(text) -> str:
    """Markdown v1 uchun foydalanuvchi matnini xavfsiz qiladi."""
    if text is None:
        return "—"
    return escape_markdown(str(text), version=1)


def format_phone(phone_raw: str) -> str:
    """Convert any phone format to +998XXXXXXXXX"""
    if not phone_raw or not isinstance(phone_raw, str):
        raise ValueError("Telefon raqami bo'sh yoki noto'g'ri formatda.")

    phone = ''.join(filter(str.isdigit, phone_raw.strip()))
    if not phone:
        raise ValueError("Telefon raqamida raqam yo'q.")

    if phone.startswith('998'):
        phone = phone[3:]
    elif phone.startswith('8') and len(phone) == 10:
        phone = phone[1:]
    elif phone.startswith('0'):
        phone = phone[1:]

    if len(phone) != 9:
        raise ValueError(f"Telefon raqami noto'g'ri: 9 ta raqam bo'lishi kerak, {len(phone)} ta topildi.")

    return f"+998{phone}"


def safe_callback_int(data: str, sep: str = "_", index: int = -1) -> int | None:
    """Callback data dan int qiymatni xavfsiz chiqaradi."""
    try:
        parts = data.split(sep)
        return int(parts[index])
    except (IndexError, ValueError):
        return None


def _schedule_sla(context, group_id: int, ism: str):
    """15 va 30 daqiqali SLA eslatmalarini rejalashtiradi."""
    context.job_queue.run_once(
        check_sla_timeout,
        when=SLA_TIMEOUT_SEC,
        data={"group_id": group_id, "x_ism": ism, "reminder": 1},
        name=f"sla_{group_id}_1",
    )
    context.job_queue.run_once(
        check_sla_timeout,
        when=SLA_TIMEOUT_SEC * 2,
        data={"group_id": group_id, "x_ism": ism, "reminder": 2},
        name=f"sla_{group_id}_2",
    )


async def _send_buffered(
    context, msg, uid: int, ism: str, lavozim: str, filial: str, topic_id: int, buf: list
):
    """Buferdagi barcha xabarlarni admin guruhiga yuboradi."""
    group_id = await db.create_xabar_guruhi(uid, ism, filial, topic_id)
    for entry in buf:
        await db.insert_xabar(uid, ism, filial, entry.get("ctype", "💬 Xabar"), entry["msg_id"], group_id)

    # Turlari bo'yicha ajratish
    text_items  = [b for b in buf if b["type"] == "text"]
    loc_items   = [b for b in buf if b["type"] == "location"]
    media_items = [b for b in buf if b["type"] in ("photo", "video")]
    other_items = [b for b in buf if b["type"] == "other"]

    now_str = datetime.now().strftime("%H:%M")

    # Header matni: ism, filial, vaqt + matnlar + lokatsiya koordinatalari
    caption_parts = [
        f"📬 *So'rov #{group_id}*",
        f"👤 {em(ism)} | 🏢 {em(filial)} | 🕐 {now_str}",
    ]
    for t in text_items:
        caption_parts.append(f"\n💬 {em(t.get('text', ''))}")
    for l in loc_items:
        caption_parts.append(f"📍 `{l['lon']:.6f}; {l['lat']:.6f}`")
    info_text = "\n".join(caption_parts)
    # Caption max 1024 chars for media; truncate if needed
    caption_for_media = info_text if len(info_text) <= 1024 else info_text[:1021] + "..."

    async def _post_to_group():
        # 1. Media group with combined caption, OR text-only message
        if media_items:
            if len(media_items) == 1:
                b = media_items[0]
                if b["type"] == "photo":
                    await context.bot.send_photo(
                        chat_id=GROUP_CHAT_ID,
                        message_thread_id=topic_id,
                        photo=b["file_id"],
                        caption=caption_for_media,
                        parse_mode="Markdown",
                    )
                else:
                    await context.bot.send_video(
                        chat_id=GROUP_CHAT_ID,
                        message_thread_id=topic_id,
                        video=b["file_id"],
                        caption=caption_for_media,
                        parse_mode="Markdown",
                    )
            else:
                media_group = []
                for i, b in enumerate(media_items):
                    cap = caption_for_media if i == 0 else None
                    pm  = "Markdown" if cap else None
                    if b["type"] == "photo":
                        media_group.append(InputMediaPhoto(media=b["file_id"], caption=cap, parse_mode=pm))
                    else:
                        media_group.append(InputMediaVideo(media=b["file_id"], caption=cap, parse_mode=pm))
                for chunk in range(0, len(media_group), 10):
                    await context.bot.send_media_group(
                        chat_id=GROUP_CHAT_ID,
                        message_thread_id=topic_id,
                        media=media_group[chunk:chunk + 10],
                    )
        else:
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic_id,
                text=info_text,
                parse_mode="Markdown",
            )
        # 2. Boshqa xabarlar (ovoz, stiker, fayl, ...)
        for item in other_items:
            await context.bot.copy_message(
                chat_id=GROUP_CHAT_ID,
                from_chat_id=item["chat_id"],
                message_id=item["msg_id"],
                message_thread_id=topic_id,
            )
        # 4. Footer — amal tugmalari (eng pastda)
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            message_thread_id=topic_id,
            text=f"⬇️ *#{group_id}* uchun amalni tanlang:",
            parse_mode="Markdown",
            reply_markup=group_sorov_inline(group_id),
        )

    try:
        await _post_to_group()
        notif = await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📬 *Yangi topshiriq!*\n{info_text}",
            parse_mode="Markdown",
            reply_markup=group_sorov_inline(group_id),
        )
        # Admin reply yo'naltirish uchun: notif msg_id → (group_id, xodim uid)
        context.bot_data.setdefault("admin_notif_map", {})[notif.message_id] = (group_id, uid)

        await msg.reply_text(
            f"✅ #{group_id}-sonli so'rovingiz qabul qilindi. Admin javobini kuting.",
            reply_markup=_role_keyboard(lavozim),
        )

        checker_id = await db.get_biriktirish(uid) if lavozim == "Agent" else None
        if checker_id:
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"#{group_id} topshiriqning muhimlilik darajasini tanlang:",
                    reply_markup=urgency_kb(group_id),
                )
            except Exception:
                pass
            context.job_queue.run_once(
                urgency_timeout_job,
                when=URGENCY_TIMEOUT_SEC,
                data={"group_id": group_id, "checker_id": checker_id, "ism": ism},
                name=f"urgency_{group_id}",
            )
            context.job_queue.run_once(
                checker_timeout_job,
                when=CHECKER_TIMEOUT_SEC,
                data={"group_id": group_id, "ism": ism},
                name=f"checker_timeout_{group_id}",
            )
        else:
            _schedule_sla(context, group_id, ism)

    except BadRequest as e:
        if "message thread not found" in str(e).lower():
            await db.reset_topic(uid)
            await msg.reply_text(
                "⚠️ Guruhdagi kanalingiz o'chirilgan. Qayta tasdiqlash kutilmoqda.",
                reply_markup=_role_keyboard(lavozim),
            )
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🔄 *Mavzusi o'chirilgan xodim:*\n\n👤 {ism} | {lavozim}",
                parse_mode="Markdown",
                reply_markup=tasdiq_inline(uid),
            )
        else:
            logger.error(f"Buferlangan xabar yuborishda xato (uid={uid}): {e}")
            await msg.reply_text("❌ Xato yuz berdi. Qayta urinib ko'ring.", reply_markup=_role_keyboard(lavozim))
    except Exception as e:
        logger.error(f"Buferlangan xabar yuborishda xato (uid={uid}): {e}")
        await msg.reply_text("❌ Xato yuz berdi. Qayta urinib ko'ring.", reply_markup=_role_keyboard(lavozim))


def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        # DB dagi adminlar ro'yxatini tekshir (asosiy ADMIN_ID ham shu jadvalda)
        if not await db.is_admin(uid):
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


def _format_profil(row: tuple) -> str:
    uid, ism, lavozim, kod, filial, tel1, tel2, tug_kun, topic_id, status, sana = row
    STATUS_TEXT = {"approved": "✅ Tasdiqlangan", "pending": "⏳ Kutilmoqda", "blocked": "🚫 Bloklangan"}
    sana_short = sana[:10] if sana else "—"
    return (
        f"👤 *{em(ism)}*\n\n"
        f"💼 Lavozim: {em(lavozim)}\n"
        f"🔑 Kod: `{em(kod)}`\n"
        f"🏢 Filial: {em(filial)}\n"
        f"📱 Tel 1: {em(tel1 or '—')}\n"
        f"📱 Tel 2: {em(tel2 or '—')}\n"
        f"🎂 Tug'ilgan kun: {em(tug_kun or '—')}\n"
        f"📅 Ro'yxat: {em(sana_short)}\n"
        f"🆔 ID: `{uid}`\n"
        f"📊 Holat: {STATUS_TEXT.get(status, '❓')}"
    )
