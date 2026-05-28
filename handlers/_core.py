import logging
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from functools import wraps

from telegram import Update, BotCommand, ReplyParameters, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
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
    klientlar_search_page_inline,
    mening_klientlar_kb,
    agent_kb, supervisor_kb, filial_rahbari_kb,
    instruksiya_lavozim_kb, instruksiya_mavjud_kb,
)


def _role_keyboard(lavozim: str):
    """Return the correct reply keyboard based on role."""
    if lavozim == "Agent":
        return agent_kb()
    if lavozim == "Filial Rahbari":
        return filial_rahbari_kb()
    return supervisor_kb()
from utils import (
    is_topic_valid, check_sla_timeout, generate_excel, generate_klientlar_excel, generate_full_excel,
    urgency_timeout_job, checker_timeout_job,
)
from telegram import InputMediaPhoto, InputMediaVideo

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
    KLIENT_LIMIT, KLIENT_CONFIRM,
    INSTR_MATN, ADD_ADMIN_ID,
)

logger = logging.getLogger(__name__)

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

_YUBORISH_BTN = "📤 Yuborish"

def _yuborish_kb():
    return ReplyKeyboardMarkup([[_YUBORISH_BTN]], resize_keyboard=True)


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
    """Buferdagi barcha xabarlarni admin guruhiga yuboradi. Rasm/video media group sifatida."""
    group_id = await db.create_xabar_guruhi(uid, ism, filial, topic_id)
    for entry in buf:
        await db.insert_xabar(uid, ism, filial, entry.get("ctype", "💬 Xabar"), entry["msg_id"], group_id)

    async def _post_to_group():
        # Header kartasi
        now_str = datetime.now().strftime("%H:%M")
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            message_thread_id=topic_id,
            text=(
                f"📬 *So'rov #{group_id}*\n"
                f"👤 {em(ism)} | 🏢 {filial} | 🕐 {now_str}"
            ),
            parse_mode="Markdown",
            reply_markup=group_sorov_inline(group_id),
        )
        # Xabarlarni ketma-ket yuborish: rasm/video → media group
        i = 0
        while i < len(buf):
            item = buf[i]
            if item["type"] in ("photo", "video"):
                # Ketma-ket media yig'ish
                media_batch = []
                while i < len(buf) and buf[i]["type"] in ("photo", "video"):
                    b = buf[i]
                    if b["type"] == "photo":
                        media_batch.append(InputMediaPhoto(media=b["file_id"], caption=b.get("caption") or ""))
                    else:
                        media_batch.append(InputMediaVideo(media=b["file_id"], caption=b.get("caption") or ""))
                    i += 1
                # InputMedia caption faqat birinchisida bo'lsin
                for j in range(1, len(media_batch)):
                    media_batch[j] = type(media_batch[j])(media=media_batch[j].media, caption="")
                for chunk in range(0, len(media_batch), 10):
                    await context.bot.send_media_group(
                        chat_id=GROUP_CHAT_ID,
                        message_thread_id=topic_id,
                        media=media_batch[chunk:chunk + 10],
                    )
            else:
                await context.bot.copy_message(
                    chat_id=GROUP_CHAT_ID,
                    from_chat_id=item["chat_id"],
                    message_id=item["msg_id"],
                    message_thread_id=topic_id,
                )
                i += 1

    try:
        await _post_to_group()
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📬 *Yangi topshiriq!*\n👤 {em(ism)}  |  🔢 #{group_id}",
            parse_mode="Markdown",
            reply_markup=group_sorov_inline(group_id),
        )
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


# ══════════════════════════════════════════════
# START VA RO'YXATDAN O'TISH OQIMI
# ══════════════════════════════════════════════
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Bekor qilindi.", reply_markup=remove_kb())
    return ConversationHandler.END


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()  # Har qanday davom etayotgan oqimni bekor qiladi
    uid = update.effective_user.id

    if await db.is_admin(uid):
        await update.message.reply_text(
            "👑 *Admin boshqaruv paneliga xush kelibsiz!*",
            parse_mode="Markdown",
            reply_markup=admin_kb(),
        )
        return ConversationHandler.END

    user = await db.get_xodim(uid)
    if user:
        status, topic_id, ism, lavozim, *_ = user

        if status == "blocked":
            await update.message.reply_text("❌ Profilingiz ma'muriyat tomonidan bloklangan.")
            return ConversationHandler.END

        if status == "approved":
            kb = _role_keyboard(lavozim)
            await update.message.reply_text(
                f"✅ Tizim faol, {em(ism)}!\n"
                "Istalgan topshiriq yoki hisobotingizni to'g'ridan-to'g'ri yuboring.",
                parse_mode="Markdown",
                reply_markup=kb,
            )
            return ConversationHandler.END

        await update.message.reply_text(
            "⏳ Profilingiz admin tomonidan tasdiqlanish jarayonida.",
            reply_markup=remove_kb(),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Assalomu Alaykum! Dusel Company botiga xush kelibsiz! 👋\n\n"
        "Iltimos, *Ism va Familiyangizni* kiriting:",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    return ISM


async def ism_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if len(text) < 3:
        await update.message.reply_text("❌ Ism kamida 3 ta harf bo'lishi kerak. Qayta kiriting:")
        return ISM
    context.user_data["ism"] = text
    await update.message.reply_text(
        "💼 Kompaniyada *kim bo'lib ishlaysiz?*",
        parse_mode="Markdown",
        reply_markup=lavozim_kb(),
    )
    return LAVOZIM


async def lavozim_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lavozim = update.message.text.strip()
    if lavozim not in LAVOZIMLAR:
        await update.message.reply_text(
            "❌ Iltimos, quyidagi tugmalardan birini tanlang:",
            reply_markup=lavozim_kb(),
        )
        return LAVOZIM
    context.user_data["lavozim"] = lavozim

    if lavozim in ("Agent", "Supervisor"):
        await update.message.reply_text(
            f"🔑 Sizga berilgan *{lavozim}* kodingizni kiriting:\n_(Masalan: AN100)_",
            parse_mode="Markdown",
            reply_markup=remove_kb(),
        )
        return KOD

    context.user_data["kod"] = "KOD YO'Q"
    await update.message.reply_text(
        "🏢 Ishlaydigan *Viloyat / Filialingizni* tanlang:",
        parse_mode="Markdown",
        reply_markup=filial_kb(),
    )
    return FILIAL


def _match_agent_code(kod: str):
    """
    Returns (agent_name_or_None, region) if code is valid, else None.

    Valid if:
    - Exact match in AGENT_DATABASE (case-insensitive) → (name, region)
    - OR starts with a known 2-char prefix AND 3rd char is NOT a letter → (None, region)
      e.g. "AN1", "AN100", "AN" → valid; "ANJ", "ANJ12" → invalid
    """
    upper = kod.strip().upper()

    # 1. Exact match → return name + region
    if upper in AGENT_DATABASE:
        region = AGENT_PREFIX_REGIONS.get(upper[:2])
        return AGENT_DATABASE[upper], region

    # 2. Prefix match: first 2 chars known, 3rd char (if any) must not be a letter
    prefix = upper[:2]
    region = AGENT_PREFIX_REGIONS.get(prefix)
    if region and (len(upper) <= 2 or not upper[2].isalpha()):
        return None, region

    return None


async def kod_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kod = update.message.text.strip().split()[0]  # faqat birinchi so'z
    lavozim = context.user_data.get("lavozim", "")

    if lavozim == "Agent":
        result = _match_agent_code(kod)
        if not result:
            await update.message.reply_text(
                "❌ Bunday kod topilmadi. To'g'ri agent kodini kiriting:"
            )
            return KOD
        agent_name, region = result
        context.user_data["kod"] = kod.upper()
        context.user_data["filial"] = region
        if agent_name:
            context.user_data["ism"] = agent_name
        welcome = (
            f"✅ *{agent_name} {kod.upper()} Xush kelibsiz!*\n"
            f"📍 Hudud: *{region}*\n\n"
            "📱 Telefon raqamingizni kiriting:"
            if agent_name else
            f"✅ Kod tasdiqlandi: *{kod.upper()}*\n"
            f"📍 Hudud: *{region}*\n\n"
            "📱 Telefon raqamingizni kiriting:"
        )
        await update.message.reply_text(welcome, parse_mode="Markdown", reply_markup=telefon_kb())
        return TELEFON

    if lavozim == "Supervisor":
        upper = kod.strip().upper()
        prefix = upper[:2]
        region = AGENT_PREFIX_REGIONS.get(prefix)
        if not region or (len(upper) > 2 and upper[2].isalpha()):
            await update.message.reply_text(
                "❌ Bunday supervisor kodi topilmadi.\n"
                "Format: *XX100* _(Masalan: AN100, SM100)_\n\nQayta kiriting:",
                parse_mode="Markdown",
            )
            return KOD
        context.user_data["kod"] = upper
        context.user_data["filial"] = region
        await update.message.reply_text(
            f"✅ Supervisor kodi tasdiqlandi: *{upper}*\n"
            f"📍 Hudud: *{region}*\n\n"
            "📱 Telefon raqamingizni kiriting:",
            parse_mode="Markdown",
            reply_markup=telefon_kb(),
        )
        return TELEFON

    # Boshqa lavozimlar uchun filial qo'lda tanlanadi
    context.user_data["kod"] = kod
    await update.message.reply_text(
        "🏢 Ishlaydigan *Viloyat / Filialingizni* tanlang:",
        parse_mode="Markdown",
        reply_markup=filial_kb(),
    )
    return FILIAL


async def filial_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    filial = update.message.text.strip()
    if filial not in FILIALLAR:
        await update.message.reply_text(
            "❌ Iltimos, ro'yxatdagi tugmalardan foydalaning:",
            reply_markup=filial_kb(),
        )
        return FILIAL
    context.user_data["filial"] = filial
    await update.message.reply_text(
        "📱 Telefon raqamingizni quyidagi tugma orqali yuboring:",
        reply_markup=telefon_kb(),
    )
    return TELEFON


async def telefon_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.contact:
        raw = msg.contact.phone_number
    elif msg.text:
        raw = msg.text.strip()
    else:
        await msg.reply_text("❌ Iltimos, raqam yuborish tugmasini bosing yoki yozing:", reply_markup=telefon_kb())
        return TELEFON
    try:
        context.user_data["telefon1"] = format_phone(raw)
    except ValueError:
        await msg.reply_text("❌ Telefon raqami noto'g'ri. Masalan: +998901234567\nQayta kiriting:", reply_markup=telefon_kb())
        return TELEFON
    await msg.reply_text(
        "Ikkinchi qo'shimcha telefon raqamingiz bormi?",
        reply_markup=telefon2_kb(),
    )
    return TELEFON2


async def telefon2_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        context.user_data["telefon2"] = update.message.contact.phone_number
    elif update.message.text and update.message.text.strip() == "⏭ O'tkazib yuborish":
        context.user_data["telefon2"] = "—"
    else:
        await update.message.reply_text(
            "❌ Iltimos, tugmani bosib raqamingizni ulashing yoki o'tkazib yuboring:",
            reply_markup=telefon2_kb(),
        )
        return TELEFON2
    await update.message.reply_text(
        "🎂 Tug'ilgan kuningizni kiriting:\n_(Masalan: 15.08.1995)_",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    return TUGILGAN_KUN


async def tugilgan_kun_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tkun = update.message.text.strip()
    try:
        datetime.strptime(tkun, "%d.%m.%Y")
    except ValueError:
        await update.message.reply_text(
            "❌ Format noto'g'ri. Masalan: 15.08.1995\nQayta kiriting:"
        )
        return TUGILGAN_KUN

    uid = update.effective_user.id
    d   = context.user_data

    await db.insert_xodim(
        uid, d["ism"], d["lavozim"], d["kod"], d["filial"],
        d["telefon1"], d["telefon2"], tkun,
    )
    await update.message.reply_text(
        "✅ Ma'lumotlaringiz adminga yuborildi. Tasdiqlashlarini kuting.",
        reply_markup=remove_kb(),
    )
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"🔔 *Yangi xodim ro'yxatdan o'tdi:*\n\n"
            f"👤 Ism: {em(d['ism'])}\n"
            f"💼 Lavozim: {em(d['lavozim'])}\n"
            f"🔑 Kod: `{em(d['kod'])}`\n"
            f"🏢 Viloyat: {em(d['filial'])}\n"
            f"📱 Tel 1: {em(d['telefon1'])}\n"
            f"📱 Tel 2: {em(d['telefon2'])}\n"
            f"🎂 Tug'ilgan kun: {em(tkun)}\n"
            f"🆔 Telegram ID: `{uid}`"
        ),
        parse_mode="Markdown",
        reply_markup=tasdiq_inline(uid),
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════
# XODIM XABARLARINI YO'NALTIRISH
# ══════════════════════════════════════════════
async def xodim_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.chat.id == GROUP_CHAT_ID:
        return

    uid = update.effective_user.id
    if await db.is_admin(uid):
        return

    # Ro'yxatdan o'tish, klient yoki so'rov oqimida bo'lsa o'tkazib yuborish
    if any(k in context.user_data for k in ("ism", "lavozim", "kod", "filial", "klient_data", "sorov_data", "limit_data")):
        return

    user = await db.get_xodim(uid)
    if not user:
        await msg.reply_text("❌ Siz ro'yxatdan o'tmagansiz. Botni boshlash uchun /start bosing.")
        return

    status, topic_id, ism, lavozim, filial, kod = user

    if status == "blocked":
        return
    if status == "pending":
        await msg.reply_text("⏳ Profilingiz tasdiqlanishini kuting.")
        return

    # ── "📤 Yuborish" tugmasi bosildi — bufer yuboriladi ─────────
    if msg.text == _YUBORISH_BTN:
        buf = context.user_data.pop("msg_buffer", [])
        if not buf:
            await msg.reply_text("❌ Yuborish uchun xabar yo'q.", reply_markup=_role_keyboard(lavozim))
            return
        await _send_buffered(context, msg, uid, ism, lavozim, filial, topic_id, buf)
        return

    # ── Flood himoya ──────────────────────────────────────────────
    if rate_limited(uid):
        return

    # ── Barcha xabar turlarini buferlash ─────────────────────────
    if msg.photo:
        entry = {"type": "photo", "msg_id": msg.message_id, "chat_id": msg.chat_id,
                 "file_id": msg.photo[-1].file_id, "caption": msg.caption}
        ctype = "📷 Rasm"
    elif msg.video:
        entry = {"type": "video", "msg_id": msg.message_id, "chat_id": msg.chat_id,
                 "file_id": msg.video.file_id, "caption": msg.caption}
        ctype = "🎥 Video"
    elif msg.text:
        entry = {"type": "text", "msg_id": msg.message_id, "chat_id": msg.chat_id, "text": msg.text}
        ctype = "💬 Matn"
    elif msg.document:
        entry = {"type": "other", "msg_id": msg.message_id, "chat_id": msg.chat_id}
        ctype = "📄 Fayl"
    elif msg.voice:
        entry = {"type": "other", "msg_id": msg.message_id, "chat_id": msg.chat_id}
        ctype = "🎙 Ovozli xabar"
    elif msg.video_note:
        entry = {"type": "other", "msg_id": msg.message_id, "chat_id": msg.chat_id}
        ctype = "⭕ Video-xabar"
    elif msg.sticker:
        entry = {"type": "other", "msg_id": msg.message_id, "chat_id": msg.chat_id}
        ctype = "🎭 Sticker"
    else:
        entry = {"type": "other", "msg_id": msg.message_id, "chat_id": msg.chat_id}
        ctype = "💬 Xabar"

    entry["ctype"] = ctype
    buf = context.user_data.setdefault("msg_buffer", [])
    buf.append(entry)
    if len(buf) == 1:
        await msg.reply_text(
            f"✅ {ctype} qo'shildi. Yana qo'shishingiz mumkin yoki \"📤 Yuborish\" tugmasini bosing:",
            reply_markup=_yuborish_kb(),
        )
    else:
        await msg.reply_text(f"✅ {len(buf)}-xabar qo'shildi ({ctype}).")
    return


# ══════════════════════════════════════════════
# REAKSIYALARNI MIRROR QILISH
# ══════════════════════════════════════════════
async def reaction_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Xodim private chatda reaksiya qo'ysa → guruh topicga mirror.
    Admin guruh topicda reaksiya qo'ysa → xodim private chatiga mirror.
    """
    rxn = update.message_reaction
    if not rxn or not rxn.user:
        return

    uid    = rxn.user.id
    cid    = rxn.chat.id
    msg_id = rxn.message_id
    new_rx = rxn.new_reaction  # List[ReactionType]

    # ── Admin guruhda reaksiya → xodimga mirror ──────────────────
    if cid == GROUP_CHAT_ID and uid == ADMIN_ID:
        xabar = await db.get_xabar_by_group_fwd_id(msg_id)
        if not xabar:
            return
        employee_uid, employee_msg_id = xabar
        try:
            await context.bot.set_message_reaction(
                chat_id=employee_uid,
                message_id=employee_msg_id,
                reaction=new_rx,
            )
        except Exception as e:
            logger.warning(f"Admin→xodim reaksiya mirror xato: {e}")
        return

    # ── Xodim private chatda reaksiya → guruhga mirror ───────────
    if cid != GROUP_CHAT_ID and uid != ADMIN_ID:
        group_msg_id = await db.get_group_msg_id_by_private(uid, msg_id)
        if not group_msg_id:
            return
        try:
            await context.bot.set_message_reaction(
                chat_id=GROUP_CHAT_ID,
                message_id=group_msg_id,
                reaction=new_rx,
            )
        except Exception as e:
            logger.warning(f"Xodim→guruh reaksiya mirror xato: {e}")


# ══════════════════════════════════════════════
# ADMIN GURUH TOPIC JAVOBLARI → XODIMGA YO'NALTIRISH
# ══════════════════════════════════════════════
async def admin_guruh_javob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.message_thread_id:
        return
    if msg.chat.id != GROUP_CHAT_ID or update.effective_user.id != ADMIN_ID:
        return

    row = await db.get_xodim_by_topic(msg.message_thread_id)
    if not row:
        return

    user_id, _ = row

    # Admin xodimning forward qilingan xabariga reply qilyaptimi?
    reply_to_private_id = None
    if msg.reply_to_message:
        xabar = await db.get_xabar_by_group_fwd_id(msg.reply_to_message.message_id)
        if xabar:
            reply_to_private_id = xabar[1]  # xodimning asl msg_id si

    try:
        try:
            rp = ReplyParameters(message_id=reply_to_private_id) if reply_to_private_id else None
            sent = await msg.copy(chat_id=user_id, reply_parameters=rp)
        except BadRequest:
            sent = await msg.copy(chat_id=user_id)
        # Mapping saqlash: keyingi xodim reply si uchun
        await db.insert_admin_msg_map(user_id, msg.message_id, sent.message_id)
    except Exception as e:
        logger.error(f"Admin javobini xodimga yuborishda xato (uid={user_id}): {e}")


# ══════════════════════════════════════════════
# CALLBACK HANDLER — helper funksiyalar
# ══════════════════════════════════════════════
async def _cb_user_action(query, context, action: str, target_uid: int):
    if action == "appr":
        row = await db.get_xodim(target_uid)
        if not row:
            await query.edit_message_text("❌ Xodim topilmadi.")
            return
        _, _, ism, lavozim, filial, kod = row
        role_txt = f"{lavozim} ({kod})" if kod and kod != "KOD YO'Q" else lavozim
        try:
            topic = await context.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID,
                name=f"{ism} — {role_txt} | {filial}",
            )
            await db.approve_xodim(target_uid, topic.message_thread_id)
            await query.edit_message_text(
                f"✅ *{em(ism)}* tasdiqlandi. Mavzu: *{em(ism)} — {em(role_txt)} | {em(filial)}*",
                parse_mode="Markdown",
            )
            await context.bot.send_message(
                chat_id=target_uid,
                text="🎉 Profilingiz tasdiqlandi! Botdan to'liq foydalanishingiz mumkin.",
                reply_markup=_role_keyboard(lavozim),
            )
            # General topic ga yangi xodim xabari
            full = await db.get_xodim_full(target_uid)
            if full:
                # (user_id, ism, lavozim, kod, filial, tel1, tel2, tug_kun, topic_id, status, sana)
                sana_str = full[10] or "—"
                xodim_card = (
                    f"🆕 *Yangi Xodim!*\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"👤 {em(full[1])}\n"
                    f"💼 {em(full[2])}\n"
                    f"🔑 Kod: {em(full[3] or '—')}\n"
                    f"🏢 {em(full[4])}\n"
                    f"📱 {em(full[5] or '—')}\n"
                    f"🎂 {em(full[7] or '—')}\n"
                    f"📅 {em(sana_str)}\n"
                    f"━━━━━━━━━━━━━━━"
                )
                try:
                    await context.bot.send_message(
                        chat_id=GROUP_CHAT_ID,
                        text=xodim_card,
                        parse_mode="Markdown",
                    )
                except Exception as ex:
                    logger.warning(f"General topic xodim xabari yuborishda xato: {ex}")
        except Exception as e:
            await query.edit_message_text(f"❌ Guruhda mavzu yaratib bo'lmadi: {e}")

    elif action == "reje":
        await db.reject_xodim(target_uid)
        await query.edit_message_text("❌ Ariza rad etildi.")
        try:
            await context.bot.send_message(
                chat_id=target_uid,
                text="❌ Arizangiz rad etildi. Qo'shimcha ma'lumot uchun adminga murojaat qiling.",
            )
        except Exception as e:
            logger.warning(f"Rad xabari yuborishda xato (uid={target_uid}): {e}")

    elif action == "block":
        await db.block_xodim(target_uid)
        await query.edit_message_text("🚫 Xodim bloklandi.")
        try:
            await context.bot.send_message(
                chat_id=target_uid,
                text="🚫 Profilingiz ma'muriyat tomonidan bloklandi.",
            )
        except Exception as e:
            logger.warning(f"Bloklash xabari yuborishda xato (uid={target_uid}): {e}")
        row = await db.get_xodim(target_uid)
        if row:
            # Feature 11: checker ga xabar
            if row[3] == "Agent":
                checker_id = await db.get_biriktirish(target_uid)
                if checker_id:
                    try:
                        await context.bot.send_message(
                            chat_id=checker_id,
                            text=f"🚫 *{em(row[2])}* (Agent) admin tomonidan bloklandi.",
                            parse_mode="Markdown",
                        )
                    except Exception:
                        pass
            # General topic ga xabar
            try:
                await context.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=f"🚫 Bloklandi: *{em(row[2])}* — {em(row[3])}",
                    parse_mode="Markdown",
                )
            except Exception as ex:
                logger.warning(f"General topic block xabari yuborishda xato: {ex}")

    elif action == "unbl":
        await db.unblock_xodim(target_uid)
        await query.edit_message_text("🔓 Xodim blokdan chiqarildi.")
        try:
            await context.bot.send_message(
                chat_id=target_uid,
                text="🔓 Profilingiz tiklandi! Botdan yana foydalana olasiz.",
            )
        except Exception as e:
            logger.warning(f"Blokdan ochish xabari yuborishda xato (uid={target_uid}): {e}")
        row = await db.get_xodim(target_uid)
        if row:
            # Feature 11: checker ga xabar
            if row[3] == "Agent":
                checker_id = await db.get_biriktirish(target_uid)
                if checker_id:
                    try:
                        await context.bot.send_message(
                            chat_id=checker_id,
                            text=f"🔓 *{em(row[2])}* (Agent) blokdan chiqarildi.",
                            parse_mode="Markdown",
                        )
                    except Exception:
                        pass
            # General topic ga xabar
            try:
                await context.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=f"✅ Blokdan chiqarildi: *{em(row[2])}* — {em(row[3])}",
                    parse_mode="Markdown",
                )
            except Exception as ex:
                logger.warning(f"General topic unblock xabari yuborishda xato: {ex}")


async def _cb_xod_page(query, page: int):
    rows = await db.get_approved_xodimlar()
    if not rows:
        await query.edit_message_text("👥 Tizimda faol xodimlar hozircha yo'q.")
        return
    total = len(rows)
    matn = f"👥 *Faol xodimlar ({page * PAGE_SIZE + 1}–{min((page + 1) * PAGE_SIZE, total)} / {total}):*\n\n"
    matn += "_Profil ko'rish uchun ismlardan birini bosing:_"
    await query.edit_message_text(matn, parse_mode="Markdown", reply_markup=xodimlar_page_inline(rows, page))


async def _cb_group_action(query, context, action: str, group_id: int):
    group = await db.get_group_info(group_id)
    if not group:
        await query.edit_message_text("❌ Guruh topilmadi.")
        return
    user_id, ism, filial, _, holat = group

    if action == "prog":
        if holat == "bajarildi":
            await query.answer("Bu guruh allaqachon bajarilgan!", show_alert=True)
            return
        await db.update_group_holat(group_id, "jarayonda")
        await query.edit_message_text(
            f"🔄 #{group_id}-guruh jarayonga olindi.",
            reply_markup=group_bajarildi_inline(group_id),
        )
        try:
            urgency = await db.get_group_urgency(group_id)
            URGENCY_LABEL = {"shoshilinch": "🔴 Shoshilinch", "orta": "🟡 O'rta", "oddiy": "🟢 Oddiy"}
            urgency_txt = URGENCY_LABEL.get(urgency, "—")
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🔄 #{group_id}-sonli so'rovingiz ko'rib chiqilmoqda ({urgency_txt}).",
            )
        except Exception as e:
            logger.warning(f"Guruh jarayon xabari yuborishda xato: {e}")

    elif action == "done":
        # SLA reminder joblarni bekor qilish
        for j in context.job_queue.get_jobs_by_name(f"sla_{group_id}_1"):
            j.schedule_removal()
        for j in context.job_queue.get_jobs_by_name(f"sla_{group_id}_2"):
            j.schedule_removal()

        await db.update_group_holat(group_id, "bajarildi")
        main_msg = await db.get_most_important_msg(group_id)
        await query.edit_message_text(f"✅ #{group_id}-guruh yakunlandi!")
        try:
            urgency = await db.get_group_urgency(group_id)
            URGENCY_LABEL = {"shoshilinch": "🔴 Shoshilinch", "orta": "🟡 O'rta", "oddiy": "🟢 Oddiy"}
            urgency_txt = URGENCY_LABEL.get(urgency, "—")
            rp = ReplyParameters(message_id=main_msg[2]) if main_msg else None
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ #{group_id}-sonli so'rovingiz bajarildi ({urgency_txt})!",
                reply_parameters=rp,
            )
        except Exception as e:
            logger.warning(f"Guruh bajarildi xabari yuborishda xato: {e}")

    elif action == "detail":
        msgs = await db.get_group_msgs_list(group_id)
        HOLAT_ICON = {"kutilmoqda": "⏳", "jarayonda": "🔄", "bajarildi": "✅"}
        holat_icon = HOLAT_ICON.get(group[4], "❓")
        vaqt_start = msgs[0][1][5:16].replace("-", ".") if msgs else "—"

        lines = [
            f"📋 *#{group_id}-guruh tafsilotlari*\n",
            f"👤 Xodim: {group[1]}",
            f"🏢 Filial: {group[2]}",
            f"🕒 Boshlangan: {vaqt_start}",
            f"📊 Xabarlar: {len(msgs)} ta",
        ]
        for tur, vaqt in msgs[:15]:
            lines.append(f"  {tur} — {vaqt[11:16]}")
        if len(msgs) > 15:
            lines.append(f"  ... va yana {len(msgs) - 15} ta")
        lines.append(f"\nHolat: {holat_icon} {group[4].capitalize()}")

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=group_detail_back_inline(group_id),
        )

    elif action == "rad":
        context.user_data["grp_reject_id"] = group_id
        await query.edit_message_text(
            f"❌ *#{group_id}-so'rovni rad etish*\n\n"
            "Rad etish sababini yozing:",
            parse_mode="Markdown",
        )

    elif action == "back":
        kb = (group_bajarildi_inline(group_id) if group[4] == "jarayonda"
              else group_sorov_inline(group_id))
        await query.edit_message_text(
            f"#{group_id}-guruh holati:",
            reply_markup=kb,
        )


async def _cb_task_action(query, context, action: str, task_id: int):
    task = await db.get_xabar(task_id)
    if not task:
        await query.edit_message_text("❌ Topshiriq topilmadi.")
        return
    t_uid, _, msg_id, holat = task

    if action == "prog":
        if holat == "bajarildi":
            await query.answer("Bu topshiriq allaqachon bajarilgan!", show_alert=True)
            return
        await db.update_xabar_holat(task_id, "jarayonda")
        await query.edit_message_text(f"🔄 #{task_id} jarayonga olindi.", reply_markup=bajarildi_inline(task_id))
        try:
            await context.bot.send_message(
                chat_id=t_uid,
                text=f"🔄 #{task_id}-sonli so'rovingiz ko'rib chiqilmoqda.",
                reply_parameters=ReplyParameters(message_id=msg_id),
            )
        except Exception as e:
            logger.warning(f"Jarayon xabari yuborishda xato (uid={t_uid}): {e}")

    elif action == "done":
        await db.update_xabar_holat(task_id, "bajarildi")
        await query.edit_message_text(f"✅ #{task_id}-sonli vazifa yakunlandi!")
        try:
            await context.bot.send_message(
                chat_id=t_uid,
                text=f"✅ #{task_id}-sonli so'rov bajarildi.",
                reply_parameters=ReplyParameters(message_id=msg_id),
            )
        except Exception as e:
            logger.warning(f"Bajarildi xabari yuborishda xato (uid={t_uid}): {e}")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    await query.answer()

    # ── Urgency tanlash (agent tomonidan) ─────────────────────────
    if data.startswith("urgency_"):
        parts = data.split("_")
        if len(parts) < 3:
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
            return
        try:
            group_id = int(parts[1])
            level = "_".join(parts[2:]) if len(parts) > 2 else ""
            if not level or level not in ("shoshilinch", "orta", "oddiy"):
                await query.answer("❌ Noto'g'ri muhimlik darajasi.", show_alert=True)
                return
        except (IndexError, ValueError):
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
            return
        URGENCY_LABEL = {"shoshilinch": "🔴 Shoshilinch", "orta": "🟡 O'rta", "oddiy": "🟢 Oddiy"}
        label = URGENCY_LABEL.get(level, level)

        await db.set_urgency(group_id, level)
        await query.edit_message_text(
            f"#{group_id} topshiriq: *{label}* deb belgilandi.", parse_mode="Markdown"
        )

        # Timeout jobni bekor qilish
        for j in context.job_queue.get_jobs_by_name(f"urgency_{group_id}"):
            j.schedule_removal()

        group = await db.get_group_info(group_id)
        if not group:
            return
        agent_uid, agent_ism, _, topic_id, _ = group
        checker_id = await db.get_biriktirish(agent_uid)

        # Guruh topicga urgency belgisi
        try:
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic_id,
                text=f"{label} — #{group_id} topshiriq",
                parse_mode="Markdown",
                disable_notification=(level != "shoshilinch"),
            )
        except Exception:
            pass

        # Checker ga xabar yuborish
        if checker_id:
            fwd_id = await db.get_latest_group_fwd_id(group_id)
            alert_prefix = "🚨 *SHOSHILINCH!* " if level == "shoshilinch" else ""
            try:
                if fwd_id:
                    await context.bot.forward_message(
                        chat_id=checker_id, from_chat_id=GROUP_CHAT_ID, message_id=fwd_id
                    )
                await context.bot.send_message(
                    chat_id=checker_id,
                    text=(
                        f"{alert_prefix}📋 *{em(agent_ism)}* #{group_id} topshiriq yubordi.\n"
                        f"{label}\nKo'rib chiqing:"
                    ),
                    parse_mode="Markdown",
                    reply_markup=checker_sorov_kb(group_id),
                )
            except Exception as e:
                logger.warning(f"Checker ga urgency xabari yuborishda xato: {e}")
        return

    # ── Checker callback (admin bo'lmagan xodimlar uchun) ─────────
    if data.startswith("bir_tasd_"):
        group_id = safe_callback_int(data, "_", 2)
        if not group_id:
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
            return
        checker = query.from_user.id
        group     = await db.get_group_info(group_id)
        if not group:
            await query.edit_message_text("❌ Topshiriq topilmadi.")
            return
        agent_uid, agent_ism = group[0], group[1]
        if await db.get_biriktirish(agent_uid) != checker:
            await query.answer("Siz bu topshiriqni tasdiqlash huquqiga ega emassiz.", show_alert=True)
            return
        checker_row  = await db.get_xodim(checker)
        checker_ism  = checker_row[2] if checker_row else "Tekshiruvchi"
        await db.update_checker_faollik(checker)

        # Checker timeout jobni bekor qilish
        for j in context.job_queue.get_jobs_by_name(f"checker_timeout_{group_id}"):
            j.schedule_removal()

        await query.edit_message_text(f"✅ #{group_id} topshiriqni tasdiqladingiz!")
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"✅ *{em(checker_ism)}* #{group_id} topshiriqni tasdiqladi!\n"
                f"👤 Agent: *{em(agent_ism)}*\n"
                f"⏳ _15 daqiqali tekshiruv boshlanadi._"
            ),
            parse_mode="Markdown",
            reply_markup=group_sorov_inline(group_id),
        )
        _schedule_sla(context, group_id, agent_ism)
        return

    if data.startswith("bir_rad_"):
        group_id = safe_callback_int(data, "_", 2)
        if not group_id:
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
            return
        checker = query.from_user.id
        group     = await db.get_group_info(group_id)
        if not group:
            await query.edit_message_text("❌ Topshiriq topilmadi.")
            return
        agent_uid, agent_ism = group[0], group[1]
        if await db.get_biriktirish(agent_uid) != checker:
            await query.answer("Siz bu topshiriqni rad etish huquqiga ega emassiz.", show_alert=True)
            return
        await db.update_checker_faollik(checker)

        # Checker timeout jobni bekor qilish
        for j in context.job_queue.get_jobs_by_name(f"checker_timeout_{group_id}"):
            j.schedule_removal()

        await db.update_group_holat(group_id, "rad etildi")
        checker_row = await db.get_xodim(checker)
        checker_ism = checker_row[2] if checker_row else "Tekshiruvchi"
        await query.edit_message_text(f"❌ #{group_id} topshiriqni rad etdingiz.")
        try:
            await context.bot.send_message(
                chat_id=agent_uid,
                text=(
                    f"❌ #{group_id}-sonli topshiriqingiz *{em(checker_ism)}* tomonidan rad etildi."
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Agent ga rad xabari yuborishda xato: {e}")
        return

    if query.from_user.id != ADMIN_ID:
        return

    if data.startswith("xodim_profil_"):
        uid = safe_callback_int(data, "_", 2)
        if not uid:
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
            return
        row = await db.get_xodim_full(uid)
        if not row:
            await query.edit_message_text("❌ Xodim topilmadi.")
            return
        await query.edit_message_text(
            _format_profil(row),
            parse_mode="Markdown",
            reply_markup=xodim_profil_kb(uid, row[9], row[2]),
        )
        return

    if data.startswith("xodim_setgroup_"):
        uid = safe_callback_int(data, "_", 2)
        if uid is None:
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
            return
        context.user_data["pending_setgroup_uid"] = uid
        row = await db.get_xodim(uid)
        ism = row[2] if row else str(uid)
        await query.edit_message_text(
            f"🔗 *{em(ism)}* uchun guruh ID sini yuboring:\n\n"
            "_Masalan: \\-1001234567890_\n"
            "_Guruhdan ID olish: @username\\_to\\_id\\_bot ni guruhga qo'shing_",
            parse_mode="Markdown",
        )
        return

    if data.startswith(("appr_", "reje_", "block_", "unbl_")):
        try:
            action, uid = data.split("_", 1)[0], int(data.split("_", 1)[1])
            await _cb_user_action(query, context, action, uid)
        except (ValueError, IndexError):
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)

    elif data.startswith("xod_page_"):
        page = safe_callback_int(data, "_", 2)
        if page is None:
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
            return
        await _cb_xod_page(query, page)

    elif data.startswith("pending_page_"):
        page = safe_callback_int(data, "_", 2)
        if page is None:
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
            return
        rows = await db.get_pending_xodimlar()
        await _send_pending_page(query.edit_message_text, rows, page)

    elif data.startswith("blocked_page_"):
        page = safe_callback_int(data, "_", 2)
        if page is None:
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
            return
        rows = await db.get_blocked_xodimlar()
        await _send_blocked_page(query.edit_message_text, rows, page)

    elif data.startswith(("grp_prog_", "grp_done_", "grp_detail_", "grp_back_", "grp_rad_")):
        parts = data.split("_")
        if len(parts) < 3:
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
            return
        try:
            action = parts[1]
            group_id = int(parts[2])
            await _cb_group_action(query, context, action, group_id)
        except (IndexError, ValueError):
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)

    elif data.startswith(("prog_", "done_")):
        parts = data.split("_", 1)
        if len(parts) < 2:
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
            return
        try:
            action = parts[0]
            task_id = int(parts[1])
            await _cb_task_action(query, context, action, task_id)
        except (IndexError, ValueError):
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)

    # Klient callbacks
    elif data.startswith("klient_view_"):
        await klient_view_callback(update, context)

    elif data.startswith("klient_approve_"):
        await klient_approve_callback(update, context)

    elif data.startswith("klient_reject_"):
        await klient_reject_callback(update, context)

    elif data == "excel_xodimlar":
        await query.answer()
        await query.edit_message_text("📊 Xodimlar hisoboti tayyorlanmoqda...")
        x_data   = await db.get_all_xodimlar_for_excel()
        m_data   = await db.get_all_xabarlar_for_excel()
        filename = await generate_excel(x_data, m_data)
        with open(filename, "rb") as f:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                caption="📊 Dusel Company — Xodimlar hisoboti.",
                filename=filename,
            )
        os.remove(filename)

    elif data == "excel_klientlar":
        await query.answer()
        await query.edit_message_text("🏪 Ochilgan klientlar Excel tayyorlanmoqda...")
        rows = await db.get_opened_klientlar_for_excel()
        if not rows:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="🏪 Ochilgan klientlar mavjud emas.",
            )
            return
        filename = await generate_klientlar_excel(rows)
        with open(filename, "rb") as f:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                caption=f"🏪 Ochilgan klientlar ({len(rows)} ta) — {__import__('datetime').date.today().strftime('%d.%m.%Y')}",
                filename=filename,
            )
        os.remove(filename)

    elif data == "excel_fulldb":
        await query.answer()
        await query.edit_message_text("🗄 To'liq DB eksport tayyorlanmoqda...")
        full_data = {
            "xodimlar":    await db.get_all_xodimlar_for_excel(),
            "topshiriqlar": await db.get_xabar_guruhi_for_excel(),
            "klientlar":   await db.get_all_klientlar_full_for_excel(),
            "sorovlar":    await db.get_sorovlar_for_excel(),
            "biriktirish": await db.get_all_biriktirish_detailed(),
            "baholash":    await db.get_baholash_for_excel(),
            "audit_log":   await db.get_audit_log_for_excel(),
        }
        total = sum(len(v) for v in full_data.values())
        filename = await generate_full_excel(full_data)
        today = __import__('datetime').date.today().strftime('%d.%m.%Y')
        with open(filename, "rb") as f:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                caption=f"🗄 To'liq DB eksport — {today}\nJami: {total} ta yozuv",
                filename=f"DuselDB_{today.replace('.','_')}.xlsx",
            )
        os.remove(filename)

    elif data.startswith("klientlar_page_"):
        page = safe_callback_int(data, "_", 2)
        if page is None:
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
            return
        rows = await db.get_all_klientlar()
        from keyboards import klientlar_page_inline
        matn = f"🏪 *Klientlar* ({len(rows)} ta)"
        await query.edit_message_text(matn, parse_mode="Markdown", reply_markup=klientlar_page_inline(rows, page))

    elif data == "klient_search_start":
        context.user_data["awaiting_klient_search"] = True
        await query.edit_message_text(
            "🔍 *Klient qidirish*\n\n"
            "_Firma nomi, INN, distributor yoki telefon raqamini kiriting:_",
            parse_mode="Markdown",
        )

    elif data.startswith("klientlar_search_page_"):
        # safe_callback_int splits by "_" at index — use manual split for 3-part prefix
        try:
            page = int(data.split("_")[-1])
        except ValueError:
            await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
            return
        results = context.user_data.get("klient_search_results", [])
        if not results:
            await query.edit_message_text("🔍 Qidiruv natijalari topilmadi. Qaytadan qidiring.")
            return
        q = context.user_data.get("klient_search_query", "")
        matn = f"🔍 *'{em(q)}' bo'yicha natijalar* ({len(results)} ta)"
        await query.edit_message_text(
            matn, parse_mode="Markdown",
            reply_markup=klientlar_search_page_inline(results, page),
        )


# ══════════════════════════════════════════════
# ADMIN PANEL HANDLERLARI
# ══════════════════════════════════════════════
@admin_only
async def admin_statistika(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stat = await db.get_statistika()
    await update.message.reply_text(
        f"📊 *Umumiy Vazifalar Statistikasi:*\n\n"
        f"📥 Jami kelgan xabarlar: *{stat['jami']}* ta\n"
        f"✅ Muvaffaqiyatli bajarilgan: *{stat['bajarilgan']}* ta\n"
        f"⏳ Kutilmoqda: *{stat['kutilmoqda']}* ta\n"
        f"⏱ O'rtacha bajarilish vaqti: *{stat['ortacha']} daqiqa*",
        parse_mode="Markdown",
    )


@admin_only
async def admin_xodimlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import XODIM_LIST
    rows = await db.get_approved_xodimlar()
    if not rows:
        await update.message.reply_text("👥 Tizimda faol xodimlar hozircha yo'q.")
        return ConversationHandler.END
    context.user_data["xodim_rows"] = rows
    total = len(rows)
    await update.message.reply_text(
        f"👥 *Faol xodimlar ({min(PAGE_SIZE, total)} / {total}):*\n\n"
        "_Profil ko'rish, tahrirlash yoki qidirish uchun tugmalardan foydalaning:_",
        parse_mode="Markdown",
        reply_markup=xodimlar_edit_page_inline(rows, page=0),
    )
    return XODIM_LIST


async def _xodim_list_page_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pagination in unified employee list."""
    from config import XODIM_LIST
    query = update.callback_query
    await query.answer()
    try:
        page = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await query.answer("❌ Xato ma'lumot", show_alert=True)
        return XODIM_LIST
    rows = context.user_data.get("xodim_rows") or await db.get_approved_xodimlar()
    context.user_data["xodim_rows"] = rows
    total = len(rows)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    await query.edit_message_text(
        f"👥 *Faol xodimlar ({start + 1}–{end} / {total}):*\n\n"
        "_Profil ko'rish, tahrirlash yoki qidirish uchun tugmalardan foydalaning:_",
        parse_mode="Markdown",
        reply_markup=xodimlar_edit_page_inline(rows, page),
    )
    return XODIM_LIST


async def _xodim_info_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View employee profile from unified list."""
    from config import XODIM_LIST
    query = update.callback_query
    await query.answer()
    try:
        uid = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await query.answer("❌ Xato ma'lumot", show_alert=True)
        return XODIM_LIST
    row = await db.get_xodim_full(uid)
    if not row:
        await query.edit_message_text("❌ Xodim topilmadi.")
        return XODIM_LIST
    matn = _format_profil(row)
    await query.edit_message_text(matn, parse_mode="Markdown", reply_markup=xodim_profil_kb(uid, row[9], row[2]))
    return XODIM_LIST


async def _xodim_edit_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start editing employee from unified list."""
    query = update.callback_query
    await query.answer()
    try:
        target_uid = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await query.answer("❌ Xato ma'lumot", show_alert=True)
        return EDIT_FIELD
    row = await db.get_xodim(target_uid)
    if not row:
        await query.edit_message_text("❌ Xodim topilmadi.")
        return EDIT_FIELD
    _, _, ism, lavozim, filial, _ = row
    context.user_data["edit_uid"] = target_uid
    await query.edit_message_text(f"✅ *{ism}* ({lavozim} | {filial}) tanlandi.", parse_mode="Markdown")
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Qaysi ma'lumotni o'zgartirmoqchisiz?",
        reply_markup=edit_field_kb(),
    )
    return EDIT_FIELD


async def _xodim_search_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start search in unified employee menu."""
    from config import SEARCH_QUERY
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔍 Xodimning *ismi* yoki *Telegram ID* sini kiriting:",
        parse_mode="Markdown",
    )
    return SEARCH_QUERY


async def _send_pending_page(send_fn, rows: list, page: int):
    total = len(rows)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    matn = f"⏳ *Kutilayotgan arizalar ({start + 1}–{end} / {total}):*\n\n"
    matn += "_Profil ko'rish yoki tasdiqlash uchun ismlardan birini bosing:_"
    await send_fn(matn, parse_mode="Markdown", reply_markup=pending_xodimlar_inline(rows, page))


@admin_only
async def admin_kutilayotganlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await db.get_pending_xodimlar()
    if not rows:
        await update.message.reply_text("✅ Kutilayotgan arizalar yo'q.")
        return
    await _send_pending_page(update.message.reply_text, rows, page=0)


async def _send_blocked_page(send_fn, rows: list, page: int):
    total = len(rows)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    matn = f"🚫 *Bloklanganlar ({start + 1}–{end} / {total}):*\n\n"
    matn += "_Profil ko'rish yoki blokdan ochish uchun ismlardan birini bosing:_"
    await send_fn(matn, parse_mode="Markdown", reply_markup=blocked_xodimlar_inline(rows, page))


@admin_only
async def admin_bloklanganlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await db.get_blocked_xodimlar()
    if not rows:
        await update.message.reply_text("🚫 Bloklanganlar mavjud emas.")
        return
    await _send_blocked_page(update.message.reply_text, rows, page=0)


@admin_only
async def admin_excel_eksport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from keyboards import excel_menu_kb
    await update.message.reply_text(
        "📥 *Excel hisobotini tanlang:*",
        parse_mode="Markdown",
        reply_markup=excel_menu_kb(),
    )


async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await db.is_admin(uid):
        return ConversationHandler.END
    await update.message.reply_text(
        "➕ *Admin qo'shish*\n\nYangi adminning *User ID* sini yuboring:\n\n"
        "💡 User ID ni bilish uchun @userinfobot ga `/start` yuboring.",
        parse_mode="Markdown",
    )
    return ADD_ADMIN_ID


async def add_admin_id_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await db.is_admin(uid):
        return ConversationHandler.END
    text = update.message.text.strip()
    if not text.lstrip("-").isdigit():
        await update.message.reply_text("❌ Faqat son kiriting (masalan: `123456789`).", parse_mode="Markdown")
        return ADD_ADMIN_ID
    new_id = int(text)
    if await db.is_admin(new_id):
        await update.message.reply_text(f"⚠️ `{new_id}` allaqachon admin.", parse_mode="Markdown")
        return ConversationHandler.END
    await db.add_admin(new_id)
    await update.message.reply_text(
        f"✅ `{new_id}` admin sifatida qo'shildi.\nU `/start` bosishi kerak.",
        parse_mode="Markdown",
        reply_markup=admin_kb(),
    )
    return ConversationHandler.END


async def instruksiya_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if await db.is_admin(uid):
        await update.message.reply_text(
            "📋 *Qaysi lavozim uchun instruksiya tahrirlaysiz?*",
            parse_mode="Markdown",
            reply_markup=instruksiya_lavozim_kb(),
        )
        return INSTR_MATN

    user = await db.get_xodim(uid)
    if not user:
        await update.message.reply_text("❌ Siz tizimda ro'yxatdan o'tmagansiz.")
        return ConversationHandler.END

    _, _, _, lavozim, *_ = user
    row = await db.get_instruksiya(lavozim)
    if row:
        matn, media_type, media_file_id = row
        caption = f"📖 *{lavozim} uchun yo'riqnoma*\n\n{matn}" if matn else f"📖 *{lavozim} uchun yo'riqnoma*"
        if media_type == "photo":
            await update.message.reply_photo(media_file_id, caption=caption, parse_mode="Markdown")
        elif media_type == "video":
            await update.message.reply_video(media_file_id, caption=caption, parse_mode="Markdown")
        else:
            await update.message.reply_text(caption, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "📖 Yo'riqnoma hali qo'shilmagan.\nAdmin tez orada qo'shadi."
        )
    return ConversationHandler.END


async def admin_instruksiya_lavozim_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lavozim = query.data[len("instr_lav_"):]
    context.user_data["instr_lavozim"] = lavozim
    row = await db.get_instruksiya(lavozim)
    if row and (row[0] or row[1]):
        matn, media_type, _ = row
        if media_type == "photo":
            preview = "📷 Rasm"
        elif media_type == "video":
            preview = "🎥 Video"
        else:
            preview = f"📝 `{matn[:120]}{'...' if len(matn or '')>120 else ''}`"
        await query.edit_message_text(
            f"📋 *{lavozim}* — joriy instruksiya:\n\n{preview}",
            parse_mode="Markdown",
            reply_markup=instruksiya_mavjud_kb(lavozim),
        )
        return INSTR_MATN
    # Mavjud emas — to'g'ridan yangi kontent so'raladi
    await query.edit_message_text(
        f"✏️ *{lavozim}* uchun instruksiya yuboring:\n\n"
        "_Matn, rasm yoki video yuborishingiz mumkin._\n_Bekor qilish: /cancel_",
        parse_mode="Markdown",
    )
    return INSTR_MATN


async def admin_instruksiya_edit_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lavozim = query.data[len("instr_edit_"):]
    context.user_data["instr_lavozim"] = lavozim
    row = await db.get_instruksiya(lavozim)
    # Agar matn bo'lsa — ko'chirib olish uchun alohida yuboriladi
    if row and row[0] and not row[1]:
        await query.message.reply_text(row[0])
    await query.edit_message_text(
        f"✏️ *{lavozim}* uchun yangi instruksiya yuboring:\n\n"
        "_Matn, rasm yoki video yuborishingiz mumkin._\n_Bekor qilish: /cancel_",
        parse_mode="Markdown",
    )
    return INSTR_MATN


async def admin_instruksiya_del_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lavozim = query.data[len("instr_del_"):]
    context.user_data.pop("instr_lavozim", None)
    async with __import__("database").get_db() as conn:
        await conn.execute("DELETE FROM instruksiyalar WHERE lavozim=?", (lavozim,))
        await conn.commit()
    await query.edit_message_text(
        f"🗑 *{lavozim}* instruksiyasi o'chirildi.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def admin_instruksiya_matn_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lavozim = context.user_data.pop("instr_lavozim", None)
    if not lavozim:
        return ConversationHandler.END

    msg = update.message
    if msg.photo:
        file_id = msg.photo[-1].file_id
        await db.set_instruksiya(lavozim, msg.caption, "photo", file_id)
        media_label = "📷 Rasm"
    elif msg.video:
        file_id = msg.video.file_id
        await db.set_instruksiya(lavozim, msg.caption, "video", file_id)
        media_label = "🎥 Video"
    else:
        await db.set_instruksiya(lavozim, msg.text.strip())
        media_label = "📝 Matn"

    await msg.reply_text(
        f"✅ *{lavozim}* uchun instruksiya saqlandi! ({media_label})",
        parse_mode="Markdown",
        reply_markup=admin_kb(),
    )
    return ConversationHandler.END


async def admin_upload_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin uchun: yuborilgan .db faylni joriy bazaga almashtiradi."""
    uid = update.effective_user.id
    if not await db.is_admin(uid):
        return

    msg = update.message
    if not msg.document:
        await msg.reply_text("❌ .db fayl yuboring.")
        return

    filename = msg.document.file_name or ""
    if not filename.endswith(".db"):
        await msg.reply_text("❌ Faqat .db fayl qabul qilinadi.")
        return

    db_path = os.path.abspath(os.environ.get("DB_PATH", "dusel_company.db"))
    backup  = db_path + ".bak"

    try:
        # Oldingi bazani backup qilib saqlaymiz
        if os.path.exists(db_path):
            import shutil
            shutil.copy2(db_path, backup)

        # Yangi faylni yuklab olamiz
        file = await msg.document.get_file()
        await file.download_to_drive(db_path)

        size_mb = os.path.getsize(db_path) / (1024 * 1024)
        await msg.reply_text(
            f"✅ Baza muvaffaqiyatli yangilandi: {size_mb:.2f} MB\n"
            f"_Oldingi baza {os.path.basename(backup)} sifatida saqlab qolindi._",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"DB yuklashda xato: {e}")
        await msg.reply_text(f"❌ Xato: {e}")


# ══════════════════════════════════════════════
# XODIMNI TAHRIRLASH OQIMI (ADMIN)
# ══════════════════════════════════════════════
async def edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = update.message.text.strip()
    if field == "❌ Bekor qilish":
        await update.message.reply_text("Tahrirlash bekor qilindi.", reply_markup=admin_kb())
        return ConversationHandler.END
    if field not in ("Ism", "Lavozim", "Kod", "Filial"):
        await update.message.reply_text("❌ Tugmalardan birini tanlang:", reply_markup=edit_field_kb())
        return EDIT_FIELD
    context.user_data["edit_field"] = field.lower()
    await update.message.reply_text(
        f"🆕 Yangi *{field}* qiymatini kiriting:",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    return EDIT_VALUE


async def edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val        = update.message.text.strip()
    field      = context.user_data.get("edit_field")
    target_uid = context.user_data.get("edit_uid")

    if not field or not target_uid:
        await update.message.reply_text("❌ Xato yuz berdi. Qaytadan boshlang.", reply_markup=admin_kb())
        return ConversationHandler.END
    await db.update_xodim_field(target_uid, field, val)
    await update.message.reply_text(
        "✅ Xodim ma'lumotlari muvaffaqiyatli yangilandi!",
        reply_markup=admin_kb(),
    )
    try:
        await context.bot.send_message(
            chat_id=target_uid,
            text=(
                f"🔔 Ma'muriyat profilingizdagi "
                f"*{field.capitalize()}* ma'lumotini yangiladi: *{val}*"
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning(f"Tahrirlash xabari yuborishda xato (uid={target_uid}): {e}")
    return ConversationHandler.END


# ══════════════════════════════════════════════
# XODIM QIDIRISH OQIMI (ADMIN)
# ══════════════════════════════════════════════
async def search_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()
    rows = await db.search_xodimlar(query_text)

    if not rows:
        await update.message.reply_text(
            f"❌ *'{em(query_text)}'* bo'yicha xodim topilmadi.\n"
            "Qayta kiriting yoki /cancel:",
            parse_mode="Markdown",
        )
        return SEARCH_QUERY

    await update.message.reply_text(
        f"🔍 *'{em(query_text)}' bo'yicha {len(rows)} ta natija:*\nXodimni tanlang:",
        parse_mode="Markdown",
        reply_markup=search_results_kb(rows),
    )
    return ConversationHandler.END


_ACTION_ICON = {
    "lokatsiya_ozgartirish": "📍",
    "raqam_ozgartirish":     "📞",
    "dokon_qoshish":         "🏪",
    "limit_qoshish":         "💰",
    "vizit_muammo":          "🖼",
    "boshqa_muammo":         "💬",
    "supervisor_tasdiqlash": "✅",
    "supervisor_rad":        "❌",
}
_ACTION_LABEL = {
    "lokatsiya_ozgartirish": "Lokatsiya o'zgartirildi",
    "raqam_ozgartirish":     "Raqam o'zgartirildi",
    "dokon_qoshish":         "Dokon qo'shildi",
    "limit_qoshish":         "Limit qo'shildi",
    "vizit_muammo":          "Vizitda muammo",
    "boshqa_muammo":         "Boshqa muammo",
    "supervisor_tasdiqlash": "Supervisor tasdiqladi",
    "supervisor_rad":        "Supervisor rad etdi",
}
_STATUS_ICON  = {"pending": "⏳", "approved": "✅", "rejected": "❌"}
_STATUS_LABEL = {"pending": "Kutilmoqda", "approved": "Tasdiqlandi", "rejected": "Rad etildi"}
_ROLE_LABEL   = {
    "agent": "agent", "supervisor": "supervisor",
    "filial_rahbari": "filial rahbari", "admin": "admin",
}


async def _send_tarix(send_fn, logs: list, filter_type: str = "all"):
    from keyboards import tarix_filter_kb
    if not logs:
        text = "📋 *O'zgarishlar tarixi bo'sh.*"
    else:
        text = "📋 *O'zgarishlar tarixi*\n\n"
        for i, row in enumerate(logs, 1):
            (_, u_id, u_role, action, target,
             old_v, new_v, status, req_id, created_at, ism) = row
            icon        = _ACTION_ICON.get(action, "📌")
            label       = _ACTION_LABEL.get(action, action)
            s_icon      = _STATUS_ICON.get(status, "—")
            s_label     = _STATUS_LABEL.get(status, status or "—")
            role_lbl    = _ROLE_LABEL.get(u_role, u_role or "—")
            user_name   = ism or ("Admin" if u_id == ADMIN_ID else str(u_id))
            target_part = f" — {em(target)}" if target else ""
            try:
                dt       = datetime.strptime(created_at[:19], "%Y-%m-%d %H:%M:%S")
                time_str = dt.strftime("%d.%m.%Y %H:%M")
            except Exception:
                time_str = (created_at or "")[:16]
            text += (
                f"{i}. 👤 *{em(user_name)}* ({role_lbl})\n"
                f"   {icon} {label}{target_part}\n"
                f"   🕐 {time_str}\n"
                f"   {s_icon} {s_label}\n\n"
            )
    await send_fn(text, parse_mode="Markdown", reply_markup=tarix_filter_kb(filter_type))


@admin_only
async def admin_tarix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    filter_type = context.user_data.get("tarix_filter", "all")
    logs = await db.get_audit_logs(filter_type=filter_type)
    await _send_tarix(update.message.reply_text, logs, filter_type)


async def tarix_filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    parts = query.data.split("_", 2)  # tarix_f_<filter>
    filter_type = parts[2] if len(parts) == 3 else "all"
    context.user_data["tarix_filter"] = filter_type
    logs = await db.get_audit_logs(filter_type=filter_type)
    await _send_tarix(query.edit_message_text, logs, filter_type)


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


# ══════════════════════════════════════════════
# BIRIKTIRISH OQIMI — TO'LIQ AGENT BOSHQARUV
# ══════════════════════════════════════════════
async def _show_biriktirish_list(send_fn):
    assigned   = await db.get_all_biriktirish_detailed()
    unassigned = await db.get_unassigned_agents()
    total = len(assigned) + len(unassigned)
    matn = f"🔗 *Biriktirish* — {total} ta agent\n\n"
    if assigned:
        matn += f"✅ Biriktirilgan: {len(assigned)} ta\n"
    if unassigned:
        matn += f"❗ Biriktirilmagan: {len(unassigned)} ta\n"
    await send_fn(
        matn,
        parse_mode="Markdown",
        reply_markup=biriktirish_list_kb(assigned, unassigned),
    )


async def _show_agent_detail(send_fn, agent_id: int):
    row = await db.get_xodim_full(agent_id)
    if not row:
        await send_fn("❌ Xodim topilmadi.")
        return False
    uid, ism, lavozim, kod, filial, tel1, tel2, tug_kun, _, status, sana = row
    checker_id  = await db.get_biriktirish(agent_id)
    checker_ism = None
    if checker_id:
        c_row = await db.get_xodim(checker_id)
        if c_row:
            last = await db.get_checker_faollik(checker_id)
            checker_ism = f"{c_row[2]} _(faollik: {last[:16] if last else '—'})_"

    stats  = await db.get_agent_today_stats(agent_id)
    STATUS_TEXT = {"approved": "✅ Faol", "pending": "⏳ Kutilmoqda", "blocked": "🚫 Bloklangan"}

    matn = (
        f"👤 *{em(ism)}*\n"
        f"💼 {em(lavozim)} | 🔑 `{em(kod)}` | 🏢 {em(filial)}\n"
        f"📱 {em(tel1 or '—')} | 🆔 `{uid}` | {STATUS_TEXT.get(status,'?')}\n\n"
        f"🔗 Checker: {checker_ism or '—'}\n\n"
        f"📊 Bugun: *{stats['bugun']}* ta | ✅ *{stats['bajarildi']}* bajarildi"
    )
    await send_fn(
        matn,
        parse_mode="Markdown",
        reply_markup=biriktir_detail_kb(uid, status, checker_id is not None),
    )
    return True


@admin_only
async def admin_biriktirish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_biriktirish_list(update.message.reply_text)
    return BIRIKTIR_AGENT


# ── BIRIKTIR_AGENT state callbacks ───────────────────────────────
async def biriktir_list_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """bir_detail_{uid} — agent detail ko'rsatish."""
    query    = update.callback_query
    await query.answer()
    try:
        agent_id = int(query.data.split("_")[2])
    except (ValueError, IndexError):
        await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
        return BIRIKTIR_AGENT
    context.user_data["biriktir_agent_id"] = agent_id
    await _show_agent_detail(query.edit_message_text, agent_id)
    return BIRIKTIR_DETAIL


async def biriktir_new_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """bir_new — biriktirilmagan agentlar ro'yxati."""
    query    = update.callback_query
    await query.answer()
    unassigned = await db.get_unassigned_agents()
    if not unassigned:
        await query.edit_message_text("✅ Barcha agentlar biriktirilgan.")
        return BIRIKTIR_AGENT
    await query.edit_message_text(
        "Agent tanlang:",
        reply_markup=biriktirish_agents_kb(unassigned),
    )
    return BIRIKTIR_AGENT


async def biriktir_agent_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """bir_agent_{uid} — agent tanlangan (yangi biriktirish uchun)."""
    query    = update.callback_query
    await query.answer()
    try:
        agent_id = int(query.data.split("_")[2])
    except (ValueError, IndexError):
        await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
        return BIRIKTIR_AGENT
    context.user_data["biriktir_agent_id"] = agent_id
    row = await db.get_xodim(agent_id)
    if not row:
        await query.edit_message_text("Xodim topilmadi.")
        return BIRIKTIR_AGENT
    _, _, ism, lavozim, filial, _ = row
    checkers = await db.get_available_checkers()
    if not checkers:
        await query.edit_message_text("Checker bo'la oladigan xodimlar topilmadi.")
        return BIRIKTIR_AGENT
    await query.edit_message_text(
        f"👤 *{em(ism)}* ({em(lavozim)} | {em(filial)})\n\nChecker tanlang:",
        parse_mode="Markdown",
        reply_markup=biriktirish_checkers_kb(checkers),
    )
    return BIRIKTIR_CHECKER


# ── BIRIKTIR_DETAIL state callbacks ──────────────────────────────
async def biriktir_back_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """bir_back — ro'yxatga qaytish."""
    query = update.callback_query
    await query.answer()
    await _show_biriktirish_list(query.edit_message_text)
    return BIRIKTIR_AGENT


async def biriktir_change_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """bir_change_{uid} — checker almashtirish."""
    query    = update.callback_query
    await query.answer()
    try:
        agent_id = int(query.data.split("_")[2])
    except (ValueError, IndexError):
        await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
        return BIRIKTIR_DETAIL
    context.user_data["biriktir_agent_id"] = agent_id
    checkers = await db.get_available_checkers()
    if not checkers:
        await query.answer("Checker bo'la oladigan xodimlar yo'q.", show_alert=True)
        return BIRIKTIR_DETAIL
    row = await db.get_xodim(agent_id)
    ism = row[2] if row else str(agent_id)
    await query.edit_message_text(
        f"👤 *{em(ism)}* uchun yangi checker tanlang:",
        parse_mode="Markdown",
        reply_markup=biriktirish_checkers_kb(checkers),
    )
    return BIRIKTIR_CHECKER


async def biriktir_rm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """bir_rm_{uid} — biriktirish o'chirish."""
    query    = update.callback_query
    await query.answer()
    try:
        agent_id = int(query.data.split("_")[2])
    except (ValueError, IndexError):
        await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
        return BIRIKTIR_AGENT
    await db.delete_biriktirish(agent_id)
    row = await db.get_xodim(agent_id)
    ism = row[2] if row else str(agent_id)
    await query.edit_message_text(f"✅ *{em(ism)}* uchun biriktirish o'chirildi.", parse_mode="Markdown")
    await _show_biriktirish_list(query.message.reply_text)
    return BIRIKTIR_AGENT


async def biriktir_block_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """bir_block_{uid} yoki bir_unblock_{uid} — bloklash."""
    query    = update.callback_query
    await query.answer()
    parts    = query.data.split("_")
    action   = parts[1]  # "block" or "unblock"
    agent_id = int(parts[2])

    if action == "block":
        await db.block_xodim(agent_id)
    else:
        await db.unblock_xodim(agent_id)

    row = await db.get_xodim_full(agent_id)
    ism = row[1] if row else str(agent_id)
    msg_text = f"🚫 *{em(ism)}* bloklandi." if action == "block" else f"🔓 *{em(ism)}* blokdan chiqarildi."
    await query.edit_message_text(msg_text, parse_mode="Markdown")
    await _show_agent_detail(query.message.reply_text, agent_id)
    return BIRIKTIR_DETAIL


async def biriktir_edit_field_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """bir_ef_{field}_{uid} — tahrirlash maydoni tanlandi."""
    query  = update.callback_query
    await query.answer()
    parts  = query.data.split("_")
    field  = parts[2]   # ism / lavozim / kod / filial
    uid    = int(parts[3])
    FIELD_LABEL = {"ism": "Ism", "lavozim": "Lavozim", "kod": "Kod", "filial": "Filial"}
    context.user_data["bir_edit_field"] = field
    context.user_data["bir_edit_uid"]   = uid
    await query.edit_message_text(
        f"🆕 *{em(FIELD_LABEL.get(field,field))}* uchun yangi qiymat kiriting:",
        parse_mode="Markdown",
    )
    return BIRIKTIR_EDIT_VALUE


async def biriktir_edit_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tahrirlash uchun yangi qiymat matn bilan kiritildi."""
    val   = update.message.text.strip()
    field = context.user_data.get("bir_edit_field")
    uid   = context.user_data.get("bir_edit_uid")
    if not field or not uid:
        await update.message.reply_text("❌ Xato. Qaytadan boshlang.")
        return ConversationHandler.END
    await db.update_xodim_field(uid, field, val)
    FIELD_LABEL = {"ism": "Ism", "lavozim": "Lavozim", "kod": "Kod", "filial": "Filial"}
    await update.message.reply_text(
        f"✅ *{em(FIELD_LABEL.get(field,field))}* yangilandi: *{em(val)}*",
        parse_mode="Markdown",
    )
    # Xodimga xabar
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=f"🔔 *{em(FIELD_LABEL.get(field,field))}* ma'lumotingiz yangilandi: *{em(val)}*",
            parse_mode="Markdown",
        )
    except Exception:
        pass
    # Detail ga qaytish
    await _show_agent_detail(update.message.reply_text, uid)
    return BIRIKTIR_DETAIL


# ── BIRIKTIR_CHECKER state callbacks ─────────────────────────────
async def biriktir_checker_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer()
    agent_id = context.user_data.get("biriktir_agent_id")
    if not agent_id:
        await query.edit_message_text("Xato. Qaytadan boshlang.")
        return ConversationHandler.END

    if query.data == "bir_none":
        await db.delete_biriktirish(agent_id)
        await query.edit_message_text("✅ Biriktirish o'chirildi.")
        await _show_agent_detail(query.message.reply_text, agent_id)
        return BIRIKTIR_DETAIL

    if query.data == "bir_back":
        await _show_biriktirish_list(query.edit_message_text)
        return BIRIKTIR_AGENT

    checker_id  = int(query.data.split("_")[2])
    await db.set_biriktirish(agent_id, checker_id)
    agent_row   = await db.get_xodim(agent_id)
    checker_row = await db.get_xodim(checker_id)
    agent_ism   = agent_row[2]   if agent_row   else str(agent_id)
    checker_ism = checker_row[2] if checker_row else str(checker_id)
    await query.edit_message_text(
        f"✅ *{em(agent_ism)}* → *{em(checker_ism)}* biriktirildi!",
        parse_mode="Markdown",
    )
    await _show_agent_detail(query.message.reply_text, agent_id)
    return BIRIKTIR_DETAIL


# ══════════════════════════════════════════════════════════════════════════════════════
# KLIENT REGISTRATSIYA OQIMI (16 QADAM)
# ══════════════════════════════════════════════════════════════════════════════════════
async def new_client_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show client registration template and initialize conversation."""
    uid = update.effective_user.id

    # Allow admin or approved xodim (not Agent)
    if uid == ADMIN_ID:
        ism = "Admin"
        context.user_data["klient_supervisor_id"] = uid
        context.user_data["klient_data"] = {}
        logger.info(f"[KLIENT] Admin {uid} starting client registration")
    else:
        user = await db.get_xodim(uid)
        if not user or user[0] != "approved" or user[3] == "Agent":
            return ConversationHandler.END
        ism = user[2]
        context.user_data["klient_supervisor_id"] = uid
        context.user_data["klient_data"] = {}
        logger.info(f"[KLIENT] User {uid} ({ism}) starting client registration")
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🔔 *{em(ism)}* yangi klient ochishni boshladi.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Admin start xabari yuborishda xato: {e}")

    template = (
        "📋 *Yangi Klient Shablon:*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ 📸 Rasm: (do'kon rasmi)\n"
        "2️⃣ 🏢 Firma nomi: Bobur Savdo\n"
        "3️⃣ 📱 Telefon 1: +998901234567\n"
        "4️⃣ 📱 Telefon 2: +998901234568\n"
        "5️⃣ 🔢 INN: 123456789\n"
        "6️⃣ 📍 Orienter: Chilonzor bozori yaqin\n"
        "7️⃣ 📌 Lokatsiya: 41.2995, 69.2401\n"
        "8️⃣ 🗂 Kategoriya: (ro'yxatdan tanlang)\n"
        "9️⃣ 🏪 Do'kon turi: (ro'yxatdan tanlang)\n"
        "🔟 👤 Distributor: Sardor\n"
        "1️⃣1️⃣ 👨 Agent/Vizit: AN001 Dushanba\n"
        "1️⃣2️⃣ 💰 Limit:\n"
        "   Cable: 1,000,000\n"
        "   Dusel: 500,000\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 Quyida kiritish boshlang:"
    )
    await update.message.reply_text(template, parse_mode="Markdown", reply_markup=remove_kb())

    await update.message.reply_text(
        "📷 *1-QADAM: Do'kon rasmi* (majburiy)\n\n"
        "_Iltimos, do'konning rasmi yuboring:_",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    logger.info(f"[KLIENT] {uid} client registration started")
    return KLIENT_RASM


async def klient_rasm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """2-qadam: rasm qabul qilish."""
    uid = update.effective_user.id

    if not update.message or not update.message.photo:
        logger.info(f"[KLIENT] {uid} - klient_rasm: Non-photo input received, requesting photo")
        await update.message.reply_text("❌ Iltimos, rasm yuboring.")
        return KLIENT_RASM

    photo_file_id = update.message.photo[-1].file_id
    context.user_data["klient_data"]["rasm_file_id"] = photo_file_id
    logger.info(f"[KLIENT] {uid} - Photo accepted: {photo_file_id[:20]}...")

    msg_sent = await update.message.reply_text(
        "📝 *2-QADAM: Firma nomi yoki Do'konchi ismi* (majburiy)\n\n"
        "_Masalan: Bobur Savdo, Xasan Dukoni, ABC Kompaniyasi_",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    logger.info(f"[KLIENT] {uid} - Transitioning to KLIENT_FIRMA_NOMI (msg_id: {msg_sent.message_id})")
    return KLIENT_FIRMA_NOMI


async def klient_firma_nomi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """3-qadam: firma nomi."""
    uid = update.effective_user.id

    if not update.message or not update.message.text:
        logger.warning(f"[KLIENT] {uid} - klient_firma_nomi: No text input")
        await update.message.reply_text(
            "❌ Iltimos, firma nomini kiriting."
        )
        return KLIENT_FIRMA_NOMI

    firma_nomi = update.message.text.strip()
    logger.info(f"[KLIENT] {uid} - Firma input: {firma_nomi}")

    if len(firma_nomi) < 2:
        logger.warning(f"[KLIENT] {uid} - Firma too short: {len(firma_nomi)} chars")
        await update.message.reply_text("❌ Firma nomi kamida 2 ta harf bo'lishi kerak.")
        return KLIENT_FIRMA_NOMI

    existing_firma = await db.check_duplicate_firma(firma_nomi)
    if existing_firma:
        logger.warning(f"[KLIENT] {uid} - Duplicate firma: {firma_nomi}")
        await update.message.reply_text(
            f"❌ *Bu firma allaqachon ro'yxatda bor!*\n\n"
            f"📝 Firma: {em(existing_firma['firma_nomi'])}\n"
            f"📱 Telefon: {em(existing_firma['telefon1'])}\n"
            f"🏪 Kategoriya: {em(existing_firma['kategoriya'])}\n\n"
            f"_Iltimos, boshqa firma nomini kiriting._",
            parse_mode="Markdown",
        )

        try:
            supervisor_name = "Admin" if uid == ADMIN_ID else (
                (await db.get_xodim(uid) or [None, None, str(uid)])[2]
            )
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"⚠️ *Dublikat Aniqlandi: Firma Nomi*\n\n"
                    f"📝 Kiritilgan firma: {em(firma_nomi)}\n"
                    f"👤 Supervisor: {em(supervisor_name)}\n"
                    f"📍 Allaqachon ro'yxatda:\n"
                    f"  • Firma: {em(existing_firma['firma_nomi'])}\n"
                    f"  • Telefon: {em(existing_firma['telefon1'])}"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Admin dublikat xabari yuborishda xato: {e}")

        return KLIENT_FIRMA_NOMI

    context.user_data["klient_data"]["firma_nomi"] = firma_nomi
    logger.info(f"[KLIENT] {uid} - Firma saved: {firma_nomi}")

    msg_sent = await update.message.reply_text(
        "📱 *3-QADAM: 1-Telefon raqami* (majburiy)\n\n"
        "_Masalan: +998901234567 yoki 901234567_",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    logger.info(f"[KLIENT] {uid} - Transitioning to KLIENT_TELEFON1 (msg_id: {msg_sent.message_id})")
    return KLIENT_TELEFON1


async def klient_telefon1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """4-qadam: telefon 1."""
    if not update.message or not update.message.text:
        await update.message.reply_text(
            "❌ Iltimos, telefon raqamini kiriting.\n"
            "_Masalan: +998901234567 yoki 998901234567_",
            reply_markup=remove_kb(),
        )
        logger.info("[KLIENT] Invalid phone input in telefon1")
        return KLIENT_TELEFON1

    phone_input = update.message.text.strip()
    logger.info(f"[KLIENT] Phone1 input: {phone_input}")

    try:
        telefon1 = format_phone(phone_input)
        logger.info(f"[KLIENT] Phone1 formatted: {telefon1}")
    except ValueError as e:
        await update.message.reply_text(
            f"❌ {str(e)}\n\n_Masalan: +998901234567 yoki 901234567_",
            reply_markup=remove_kb(),
        )
        logger.warning(f"[KLIENT] Phone1 format error: {e}")
        return KLIENT_TELEFON1

    existing_telefon = await db.check_duplicate_telefon(telefon1)
    if existing_telefon:
        uid = update.effective_user.id
        if uid == ADMIN_ID:
            await update.message.reply_text(
                f"❌ *Bu telefon raqami allaqachon ro'yxatda bor!*\n\n"
                f"📝 Firma: {em(existing_telefon['firma_nomi'])}\n"
                f"📞 Telefon: {em(existing_telefon['telefon1'])}\n"
                f"🏪 Kategoriya: {em(existing_telefon['kategoriya'])}\n\n"
                f"_Iltimos, boshqa telefon raqamini kiriting._",
                parse_mode="Markdown",
                reply_markup=remove_kb(),
            )
        else:
            await update.message.reply_text(
                "❌ Bu raqam bilan dokon allaqachon ochilgan.\n"
                "Iltimos, boshqa telefon raqamini kiriting.",
                reply_markup=remove_kb(),
            )
        return KLIENT_TELEFON1

    context.user_data["klient_data"]["telefon1"] = telefon1
    logger.info(f"[KLIENT] {update.effective_user.id} - Telefon1 saved: {telefon1}")

    msg_sent = await update.message.reply_text(
        "📱 *4-QADAM: 2-Telefon raqami* (ixtiyoriy)\n\n"
        "_Masalan: +998901234568 yoki \"⏭ O'tkazib yuborish\" tugmasini bosing_",
        parse_mode="Markdown",
        reply_markup=telefon2_kb(),
    )
    logger.info(f"[KLIENT] {update.effective_user.id} - Transitioning to KLIENT_TELEFON2 (msg_id: {msg_sent.message_id})")
    return KLIENT_TELEFON2


async def klient_telefon2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """5-qadam: telefon 2 (ixtiyoriy)."""
    if not update.message or not update.message.text:
        await update.message.reply_text(
            "❌ Iltimos, telefon raqamini kiriting yoki o'tkazib yuborish tugmasini bosing.",
            reply_markup=telefon2_kb(),
        )
        return KLIENT_TELEFON2

    text_input = update.message.text.strip()
    logger.info(f"[KLIENT] Phone2 input: {text_input}")

    if text_input == "⏭ O'tkazib yuborish":
        context.user_data["klient_data"]["telefon2"] = None
        logger.info("[KLIENT] Phone2 skipped")
    else:
        try:
            telefon2 = format_phone(text_input)
            context.user_data["klient_data"]["telefon2"] = telefon2
            logger.info(f"[KLIENT] Phone2 formatted: {telefon2}")
        except ValueError as e:
            await update.message.reply_text(
                f"❌ {str(e)}\n\n_Masalan: +998901234568 yoki \"⏭ O'tkazib yuborish\" tugmasini bosing_",
                reply_markup=telefon2_kb(),
            )
            logger.warning(f"[KLIENT] Phone2 format error: {e}")
            return KLIENT_TELEFON2

    uid = update.effective_user.id
    logger.info(f"[KLIENT] {uid} - Telefon2: {context.user_data['klient_data'].get('telefon2', 'None')}")

    msg_sent = await update.message.reply_text(
        "🔢 *5-QADAM: INN raqami* (ixtiyoriy)\n"
        "_Masalan: 123456789 yoki \"⏭ O'tkazib yuborish\" tugmasini bosing_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("⏭ O'tkazib yuborish")]],
            resize_keyboard=True, one_time_keyboard=True,
        ),
    )
    logger.info(f"[KLIENT] {uid} - Transitioning to KLIENT_INN (msg_id: {msg_sent.message_id})")
    return KLIENT_INN


async def klient_inn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """6-qadam: INN (ixtiyoriy)."""
    if update.message.text == "⏭ O'tkazib yuborish":
        context.user_data["klient_data"]["inn"] = None
    else:
        inn = update.message.text.strip()
        if inn and (not inn.isdigit() or len(inn) != 9):
            await update.message.reply_text(
                "❌ INN raqami 9 ta raqamdan iborat bo'lishi kerak yoki o'tkazib yuborish tugmasini bosing.",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("⏭ O'tkazib yuborish")]],
                    resize_keyboard=True, one_time_keyboard=True,
                ),
            )
            return KLIENT_INN
        context.user_data["klient_data"]["inn"] = inn if inn else None

    uid = update.effective_user.id
    logger.info(f"[KLIENT] {uid} - INN: {context.user_data['klient_data'].get('inn', 'None')}")

    msg_sent = await update.message.reply_text(
        "📍 *6-QADAM: Orienter* (yaqin joy tavsifi)\n"
        "_Masalan: Bazarning yonida, Mektebning oldida_",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    logger.info(f"[KLIENT] {uid} - Transitioning to KLIENT_ORIENTER (msg_id: {msg_sent.message_id})")
    return KLIENT_ORIENTER


async def klient_orienter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """6-qadam: orienter."""
    orienter = update.message.text.strip()
    if len(orienter) < 3:
        await update.message.reply_text("❌ Orienter kamida 3 ta harf bo'lishi kerak.")
        return KLIENT_ORIENTER

    context.user_data["klient_data"]["orienter"] = orienter

    await update.message.reply_text(
        "📍 *7-QADAM: Lokatsiya* (majburiy)\n\n"
        "_GPS ulashish tugmasidan yoki koordinata/manzil yozing:_\n"
        "_Masalan: 41.2995, 69.2401_",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    return KLIENT_LOKATSIYA



async def klient_lokatsiya(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """7-qadam: lokatsiya (mandatory) - qabul qiladi: share location, forwarded location, yoki text."""
    msg = update.message

    # Option 1: Accept shared/live location button or forwarded location
    if msg.location:
        try:
            context.user_data["klient_data"]["lokatsiya_lat"] = msg.location.latitude
            context.user_data["klient_data"]["lokatsiya_lon"] = msg.location.longitude
            context.user_data["klient_data"]["lokatsiya_address"] = None
            logger.info(f"[KLIENT] Location accepted: {msg.location.latitude}, {msg.location.longitude}")
        except Exception as e:
            logger.error(f"Lokatsiya xatosi: {e}")
            await msg.reply_text("❌ Lokatsiyani saqlashda xato. Qayta urinib ko'ring.")
            return KLIENT_LOKATSIYA

    # Option 2: Accept text — try "lat, lon" first, fall back to freeform address
    elif msg.text and msg.text.strip():
        text_input = msg.text.strip()
        coord_m = re.match(r'^(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)$', text_input)
        if coord_m:
            try:
                lat = float(coord_m.group(1))
                lon = float(coord_m.group(2))
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    context.user_data["klient_data"]["lokatsiya_lat"] = lat
                    context.user_data["klient_data"]["lokatsiya_lon"] = lon
                    context.user_data["klient_data"]["lokatsiya_address"] = None
                    logger.info(f"[KLIENT] Parsed text coords: {lat}, {lon}")
                else:
                    raise ValueError("out of range")
            except ValueError:
                context.user_data["klient_data"]["lokatsiya_address"] = text_input
                context.user_data["klient_data"]["lokatsiya_lat"] = None
                context.user_data["klient_data"]["lokatsiya_lon"] = None
                logger.info(f"[KLIENT] Invalid coord range, stored as address: {text_input}")
        else:
            context.user_data["klient_data"]["lokatsiya_address"] = text_input
            context.user_data["klient_data"]["lokatsiya_lat"] = None
            context.user_data["klient_data"]["lokatsiya_lon"] = None
            logger.info(f"[KLIENT] Location address accepted: {text_input}")

    else:
        await msg.reply_text(
            "❌ Lokatsiyani yuboring yoki manzilni matn ko'rinishida kiriting.",
        )
        return KLIENT_LOKATSIYA

    await context.bot.send_message(
        chat_id=msg.chat_id,
        text="🏪 *8-QADAM: Do'kon turi* (majburiy)",
        parse_mode="Markdown",
        reply_markup=klient_dokon_turi_kb(),
    )
    return KLIENT_DOKON_TURI


async def klient_dokon_turi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """8-qadam: do'kon turi (inline)."""
    query = update.callback_query
    await query.answer()

    slug = query.data[len("klient_tur_"):]
    value = DOKON_SLUGLARI.get(slug)
    if not value:
        await query.answer("❌ Noto'g'ri tanlov.", show_alert=True)
        return KLIENT_DOKON_TURI

    context.user_data["klient_data"]["kategoriya"] = value
    context.user_data["klient_data"]["dokon_turi"] = value
    logger.info(f"[KLIENT] Dokon turi selected: {value}")

    await query.edit_message_text(f"✅ Do'kon turi: *{value}*", parse_mode="Markdown")
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🚚 *9-QADAM: Distributor* (majburiy)\n\n_Distributor nomini kiriting:_",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    return KLIENT_DISTRIBUTOR


async def klient_distributor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """11-qadam: distributor - accept any text input."""
    distributor_name = update.message.text.strip()

    if not distributor_name or len(distributor_name) < 2:
        await update.message.reply_text("❌ Distributor nomi kamida 2 ta harf bo'lishi kerak. Qayta kiriting:")
        return KLIENT_DISTRIBUTOR

    context.user_data["klient_data"]["distributor"] = distributor_name
    logger.info(f"[KLIENT] Distributor accepted: {distributor_name}")

    await update.message.reply_text(
        "👨 *11-QADAM: Agent va Vizit kuni* (majburiy)\n\n"
        "_Agent kodi va vizit kunini birgalikda kiriting._\n"
        "_Masalan: AN001 Dushanba_",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    return KLIENT_AGENT_KOD


async def klient_agent_kod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """11-qadam: agent va vizit kuni - free text input."""
    if not update.message or not update.message.text:
        return KLIENT_AGENT_KOD

    agent_vizit = update.message.text.strip().split()[0].upper()
    result = _match_agent_code(agent_vizit)
    if not result:
        await update.message.reply_text(
            "❌ Bu agent kodi tizimda mavjud emas.\n"
            "Iltimos, to'g'ri agent kodini kiriting:"
        )
        return KLIENT_AGENT_KOD

    _, region = result
    context.user_data["klient_data"]["agent_vizit"] = agent_vizit
    context.user_data["klient_data"]["agent_region"] = region
    logger.info(f"[KLIENT] Agent/Vizit accepted: {agent_vizit} ({region})")

    await update.message.reply_text(
        f"✅ Agent kodi qabul qilindi: *{agent_vizit}*\n"
        f"📍 Hudud: *{region}*\n\n"
        "💰 *12-QADAM: Limit* (majburiy)\n\n"
        "_Har loyiha uchun limitni yozing. Masalan:_\n"
        "```\nCable: 1,000,000\nDusel: 500,000\nTools: 800,000\n```",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    return KLIENT_LIMIT


async def klient_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """12-qadam: limit - free text."""
    if not update.message or not update.message.text:
        return KLIENT_LIMIT

    limit_text = update.message.text.strip()
    if not limit_text:
        await update.message.reply_text("❌ Limit bo'sh bo'lmasligi kerak.")
        return KLIENT_LIMIT

    context.user_data["klient_data"]["limit_text"] = limit_text
    logger.info(f"[KLIENT] Limit accepted: {limit_text[:50]}")

    await _show_klient_summary(update.message.reply_text, context.user_data["klient_data"])
    return KLIENT_CONFIRM


def _format_lokatsiya(data: dict) -> str:
    """Return a human-readable location string from klient_data."""
    lat = data.get("lokatsiya_lat")
    lon = data.get("lokatsiya_lon")
    if lat is not None and lon is not None:
        return f"{lat:.6f}, {lon:.6f}"
    return data.get("lokatsiya_address") or "—"


async def _get_supervisor_name(supervisor_id: int, context) -> str:
    if supervisor_id == ADMIN_ID:
        return "Admin"
    user = await db.get_xodim(supervisor_id)
    return user[2] if user else str(supervisor_id)


async def _show_klient_summary(send_fn, data: dict):
    """Klient ma'lumotlarining xulasasini ko'rsatish."""
    lokatsiya = _format_lokatsiya(data)
    summary = (
        f"📋 *Klient ma'lumotlari:*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📸 Rasm: ✅\n"
        f"🏢 Firma: {em(data['firma_nomi'])}\n"
        f"📱 Tel 1: {em(data['telefon1'])}\n"
        f"📱 Tel 2: {em(data.get('telefon2') or '—')}\n"
        f"🔢 INN: {em(data.get('inn') or '—')}\n"
        f"📍 Orienter: {em(data['orienter'])}\n"
        f"📌 Lokatsiya: {em(lokatsiya)}\n"
        f"🗂 Kategoriya: {em(data['kategoriya'])}\n"
        f"🏪 Do'kon turi: {em(data['dokon_turi'])}\n"
        f"👤 Distributor: {em(data['distributor'])}\n"
        f"👨 Agent kodi: {em(data['agent_vizit'])} — 📍 {em(data.get('agent_region', ''))}\n"
        f"💰 Limit: {em(data['limit_text'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    await send_fn(summary, parse_mode="Markdown", reply_markup=klient_confirm_kb())


async def klient_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """16-qadam: tasdiqlash."""
    query = update.callback_query
    await query.answer()

    if query.data == "klient_submit":
        data = context.user_data.get("klient_data", {})
        supervisor_id = context.user_data.get("klient_supervisor_id")

        try:
            klient_id = await db.insert_klient(
                rasm_file_id=data.get("rasm_file_id"),
                firma_nomi=data.get("firma_nomi"),
                telefon1=data.get("telefon1"),
                telefon2=data.get("telefon2"),
                inn=data.get("inn"),
                orienter=data.get("orienter"),
                lokatsiya_lat=data.get("lokatsiya_lat"),
                lokatsiya_lon=data.get("lokatsiya_lon"),
                lokatsiya_address=data.get("lokatsiya_address"),
                kategoriya=data.get("kategoriya"),
                dokon_turi=data.get("dokon_turi"),
                distributor=data.get("distributor"),
                agent_kod=data.get("agent_vizit"),
                vizit_kun="",
                chastota="",
                limit_summa=data.get("limit_text"),
                brendlar="",
                supervisor_id=supervisor_id,
            )

            await query.edit_message_text("✅ Klient muvaffaqiyatli qo'shildi!")

            # ── Audit log ─────────────────────────────────────
            _uid = query.from_user.id
            if _uid == ADMIN_ID:
                _role = "admin"
            else:
                _xrow = await db.get_xodim(_uid)
                _role = {
                    "Agent": "agent", "Supervisor": "supervisor",
                    "Filial Rahbari": "filial_rahbari",
                }.get(_xrow[3] if _xrow else "", "supervisor")
            try:
                await db.insert_audit_log(
                    user_id=_uid,
                    user_role=_role,
                    action_type="dokon_qoshish",
                    target=data.get("firma_nomi"),
                    old_value=None,
                    new_value=data.get("telefon1"),
                    status="pending",
                    request_id=klient_id,
                )
            except Exception as _e:
                logger.warning(f"Audit log yozishda xato (dokon_qoshish): {_e}")
            # ──────────────────────────────────────────────────

            supervisor_name = await _get_supervisor_name(supervisor_id, context)
            lokatsiya = _format_lokatsiya(data)

            admin_card = (
                f"📋 *Yangi Klient #{klient_id}*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏢 Firma: {em(data['firma_nomi'])}\n"
                f"📱 Tel 1: {em(data['telefon1'])}\n"
                f"📱 Tel 2: {em(data.get('telefon2') or '—')}\n"
                f"🔢 INN: {em(data.get('inn') or '—')}\n"
                f"📍 Orienter: {em(data['orienter'])}\n"
                f"📌 Lokatsiya: {em(lokatsiya)}\n"
                f"🗂 Kategoriya: {em(data['kategoriya'])}\n"
                f"🏪 Do'kon turi: {em(data['dokon_turi'])}\n"
                f"👤 Distributor: {em(data['distributor'])}\n"
                f"👨 Agent kodi: {em(data['agent_vizit'])} — 📍 {em(data.get('agent_region', ''))}\n"
                f"💰 Limit: {em(data['limit_text'])}\n"
                f"👤 Supervisor: {em(supervisor_name)}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

            try:
                from keyboards import klient_approval_kb
                appr_kb = klient_approval_kb(klient_id)
                if data.get("rasm_file_id"):
                    if len(admin_card) <= 1024:
                        await context.bot.send_photo(
                            chat_id=ADMIN_ID,
                            photo=data["rasm_file_id"],
                            caption=admin_card,
                            parse_mode="Markdown",
                            reply_markup=appr_kb,
                        )
                    else:
                        await context.bot.send_photo(chat_id=ADMIN_ID, photo=data["rasm_file_id"])
                        await context.bot.send_message(
                            chat_id=ADMIN_ID, text=admin_card,
                            parse_mode="Markdown", reply_markup=appr_kb,
                        )
                else:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID, text=admin_card,
                        parse_mode="Markdown", reply_markup=appr_kb,
                    )
            except Exception as e:
                logger.warning(f"Admin xabari yuborishda xato: {e}")

            # General topic (message_thread_id=1) ga to'liq klient kartasi
            group_card = (
                f"🏪 *Yangi Klient #{klient_id}*\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🏢 {em(data['firma_nomi'])}\n"
                f"📱 {em(data['telefon1'])}\n"
                f"📍 {em(data['orienter'])}\n"
                f"📌 {em(lokatsiya)}\n"
                f"🗂 {em(data['kategoriya'])}\n"
                f"🏪 {em(data['dokon_turi'])}\n"
                f"👤 Distributor: {em(data['distributor'])}\n"
                f"👨 Agent kodi: {em(data['agent_vizit'])} — 📍 {em(data.get('agent_region', ''))}\n"
                f"💰 Limit: {em(data['limit_text'])}\n"
                f"👤 Supervisor: {em(supervisor_name)}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"⏳ Kutilmoqda"
            )
            try:
                if data.get("rasm_file_id"):
                    if len(group_card) <= 1024:
                        await context.bot.send_photo(
                            chat_id=GROUP_CHAT_ID,
                                photo=data["rasm_file_id"],
                            caption=group_card,
                            parse_mode="Markdown",
                        )
                    else:
                        await context.bot.send_photo(chat_id=GROUP_CHAT_ID, photo=data["rasm_file_id"])
                        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=group_card, parse_mode="Markdown")
                else:
                    await context.bot.send_message(
                        chat_id=GROUP_CHAT_ID,
                        text=group_card,
                        parse_mode="Markdown",
                    )
            except Exception as e:
                logger.warning(f"General topic ga klient xabari yuborishda xato: {e}")

            context.user_data.clear()
        except Exception as e:
            logger.error(f"Klient qo'shishda xato: {e}")
            await query.edit_message_text(f"❌ Xato: {e}")

        return ConversationHandler.END

    elif query.data == "klient_cancel":
        context.user_data.clear()
        await query.edit_message_text("❌ Klient registratsiyasi bekor qilindi.")
        return ConversationHandler.END


# ══════════════════════════════════════════════════════════════════════════════════════
# ADMIN KLIENT BOSHQARUVI
# ══════════════════════════════════════════════════════════════════════════════════════
@admin_only
async def admin_klientlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin - klientlar statistikasi."""
    from keyboards import klientlar_stats_kb
    stats = await db.get_klientlar_stats()
    matn = (
        f"🏪 *Klientlar*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 Jami: *{stats['total']}* ta\n"
        f"⏳ Kutilmoqda: *{stats['pending']}* ta\n"
        f"✅ Tasdiqlangan: *{stats['approved']}* ta\n"
        f"❌ Rad etilgan: *{stats['rejected']}* ta\n"
        f"━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(matn, parse_mode="Markdown", reply_markup=klientlar_stats_kb())


async def _show_klient_profile_admin(send_fn, klient_id: int, context=None):
    """Admin uchun klient profilini ko'rsatish."""
    klient = await db.get_klient(klient_id)
    if not klient:
        await send_fn("❌ Klient topilmadi.")
        return

    cols = ("id", "rasm", "firma_nomi", "telefon1", "telefon2", "inn", "orienter",
            "lat", "lon", "kategoriya", "dokon_turi", "distributor", "agent_kod",
            "vizit_kun", "chastota", "limit", "brendlar", "status", "reason", "sana", "sup_id",
            "lokatsiya_address")
    data = dict(zip(cols, klient))

    lat, lon = data.get("lat"), data.get("lon")
    if lat is not None and lon is not None:
        lokatsiya = f"{lat:.6f}, {lon:.6f}"
    else:
        lokatsiya = data.get("lokatsiya_address") or "—"

    profile = (
        f"🏪 *Klient Profili*\n\n"
        f"📝 Firma: {em(data['firma_nomi'])}\n"
        f"📱 Tel 1: {em(data['telefon1'])}\n"
        f"📱 Tel 2: {em(data['telefon2'] or '—')}\n"
        f"🔢 INN: {em(data['inn'] or '—')}\n"
        f"📍 Orienter: {em(data['orienter'])}\n"
        f"📌 Lokatsiya: {em(lokatsiya)}\n"
        f"🏪 Kategoriya: {em(data['kategoriya'])}\n"
        f"🏢 Do'kon turi: {em(data['dokon_turi'])}\n"
        f"🚚 Distributor: {em(data['distributor'])}\n"
        f"👨 Agent/Vizit: {em(data['agent_kod'])}\n"
        f"💰 Limit: {em(str(data['limit']))}\n"
        f"📊 Holat: {em(data['status'])}\n"
    )

    from keyboards import klient_approval_kb
    if data['status'] == 'pending':
        await send_fn(profile, parse_mode="Markdown", reply_markup=klient_approval_kb(klient_id))
    else:
        await send_fn(profile, parse_mode="Markdown")


async def klient_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Klient profilini ko'rish (admin callback)."""
    query = update.callback_query
    await query.answer()

    klient_id = safe_callback_int(query.data, "_", 2)
    if not klient_id:
        return

    await _show_klient_profile_admin(query.edit_message_text, klient_id, context)


async def klient_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Klientni tasdiqlash."""
    query = update.callback_query
    await query.answer()

    klient_id = safe_callback_int(query.data, "_", 2)
    if not klient_id:
        return

    klient = await db.get_klient(klient_id)
    if not klient:
        await query.answer("❌ Klient topilmadi.", show_alert=True)
        return

    await db.approve_klient(klient_id)
    await query.edit_message_text(f"✅ Klient #{klient_id} tasdiqlandi!")

    try:
        sup_id = klient[20]
        await context.bot.send_message(
            chat_id=sup_id,
            text=f"✅ Klientingiz *{em(klient[2])}* tasdiqlandi!",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning(f"Supervisor xabari yuborishda xato: {e}")


async def klient_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Klientni rad etish uchun sababni so'rash."""
    query = update.callback_query
    await query.answer()

    klient_id = safe_callback_int(query.data, "_", 2)
    if not klient_id:
        return

    context.user_data["klient_reject_id"] = klient_id
    await query.edit_message_text(
        "❌ *Rad etish sababini yozing:*\n\n"
        "_Masalan: Noto'g'ri ma'lumot, duplikat, boshqa sabab_",
        parse_mode="Markdown",
    )


async def klient_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Klientni rad etish, klient qidirish va sorov javobini yuborish."""
    if update.effective_user.id != ADMIN_ID:
        return

    # Check if admin is replying to a sorov message
    from sorov_handlers import handle_admin_sorov_reply
    if await handle_admin_sorov_reply(update, context):
        return

    # Handle supervisor group assignment
    pending_setgroup = context.user_data.get("pending_setgroup_uid")
    if pending_setgroup:
        context.user_data.pop("pending_setgroup_uid", None)
        text = update.message.text.strip()
        if text.lstrip("-").isdigit():
            group_chat_id = int(text)
            await db.set_supervisor_group(pending_setgroup, group_chat_id)
            row = await db.get_xodim(pending_setgroup)
            ism = row[2] if row else str(pending_setgroup)
            await update.message.reply_text(
                f"✅ *{em(ism)}* uchun guruh belgilandi: `{group_chat_id}`",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "❌ Noto'g'ri format. Guruh ID raqam bo'lishi kerak.\n"
                "_Masalan: -1001234567890_",
                parse_mode="Markdown",
            )
        return

    # Handle klient search input
    if context.user_data.get("awaiting_klient_search"):
        context.user_data.pop("awaiting_klient_search", None)
        q = update.message.text.strip()
        context.user_data["klient_search_query"] = q
        results = await db.search_klientlar(q)
        context.user_data["klient_search_results"] = results
        if not results:
            await update.message.reply_text(f"🔍 *'{em(q)}'* bo'yicha hech narsa topilmadi.", parse_mode="Markdown")
            return
        await update.message.reply_text(
            f"🔍 *'{em(q)}' bo'yicha natijalar* ({len(results)} ta)",
            parse_mode="Markdown",
            reply_markup=klientlar_search_page_inline(results, 0),
        )
        return

    # Handle group (so'rov) rejection reason
    grp_reject_id = context.user_data.pop("grp_reject_id", None)
    if grp_reject_id:
        reason = update.message.text.strip()
        grp = await db.get_group_info(grp_reject_id)
        if grp:
            emp_uid, emp_ism = grp[0], grp[1]
            await db.update_group_holat(grp_reject_id, "rad etildi")
            await update.message.reply_text(f"❌ #{grp_reject_id}-so'rov rad etildi!")
            try:
                await context.bot.send_message(
                    chat_id=emp_uid,
                    text=(
                        f"❌ *#{grp_reject_id}-sonli so'rovingiz rad etildi.*\n\n"
                        f"_Sabab: {em(reason)}_"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.warning(f"Rad xabari yuborishda xato (uid={emp_uid}): {e}")
        return

    klient_id = context.user_data.get("klient_reject_id")

    if not klient_id:
        return  # Ignore message if not in reject state

    reason = update.message.text.strip()
    klient = await db.get_klient(klient_id)
    if not klient:
        await update.message.reply_text("❌ Klient topilmadi.")
        context.user_data.pop("klient_reject_id", None)
        return

    await db.reject_klient(klient_id, reason)
    await update.message.reply_text(f"❌ Klient #{klient_id} rad etildi!")

    try:
        sup_id = klient[20]
        await context.bot.send_message(
            chat_id=sup_id,
            text=f"❌ Do'kon *{em(klient[2])}* rad etildi.\n\n_Sabab: {em(reason)}_",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning(f"Supervisor xabari yuborishda xato: {e}")

    context.user_data.pop("klient_reject_id", None)


# ══════════════════════════════════════════════════════════════════════════════════════
# MENING KLIENTLARIM — xodim o'z klientlarini ko'rish
# ══════════════════════════════════════════════════════════════════════════════════════

async def mening_klientlarim_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid == ADMIN_ID:
        rows = await db.get_all_klientlar()
    else:
        rows = await db.get_klientlar_by_supervisor(uid)

    context.user_data["mk_rows"] = rows

    if not rows:
        await update.message.reply_text("🏪 Hozircha klientlar yo'q.")
        return

    await update.message.reply_text(
        f"🏪 *Mening Klientlarim* ({len(rows)} ta)\n\n_Batafsil ko'rish uchun bosing:_",
        parse_mode="Markdown",
        reply_markup=mening_klientlar_kb(rows, 0),
    )


async def mk_page_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "mk_noop":
        return

    page = safe_callback_int(query.data, "_", 2)
    if page is None:
        return

    rows = context.user_data.get("mk_rows")
    if not rows:
        uid = query.from_user.id
        if uid == ADMIN_ID:
            rows = await db.get_all_klientlar()
        else:
            rows = await db.get_klientlar_by_supervisor(uid)
        context.user_data["mk_rows"] = rows

    if not rows:
        await query.edit_message_text("🏪 Hozircha klientlar yo'q.")
        return

    await query.edit_message_text(
        f"🏪 *Mening Klientlarim* ({len(rows)} ta)\n\n_Batafsil ko'rish uchun bosing:_",
        parse_mode="Markdown",
        reply_markup=mening_klientlar_kb(rows, page),
    )


async def mk_view_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # callback_data: mk_view_{klient_id}_{back_page}
    parts = query.data.split("_")
    try:
        klient_id = int(parts[2])
        back_page = int(parts[3])
    except (IndexError, ValueError):
        return

    klient = await db.get_klient(klient_id)
    if not klient:
        await query.answer("❌ Klient topilmadi.", show_alert=True)
        return

    cols = ("id", "rasm", "firma_nomi", "telefon1", "telefon2", "inn", "orienter",
            "lat", "lon", "kategoriya", "dokon_turi", "distributor", "agent_kod",
            "vizit_kun", "chastota", "limit", "brendlar", "status", "reason", "sana", "sup_id",
            "lokatsiya_address")
    data = dict(zip(cols, klient))

    lat, lon = data.get("lat"), data.get("lon")
    if lat is not None and lon is not None:
        lokatsiya = f"{lat:.6f}, {lon:.6f}"
    else:
        lokatsiya = data.get("lokatsiya_address") or "—"

    status_icon = "✅" if data["status"] == "approved" else "⏳" if data["status"] == "pending" else "❌"

    profile = (
        f"🏪 *Klient #{data['id']}*\n\n"
        f"📝 Firma: {em(data['firma_nomi'])}\n"
        f"📱 Tel 1: {em(data['telefon1'])}\n"
        f"📱 Tel 2: {em(data.get('telefon2') or '—')}\n"
        f"🔢 INN: {em(data.get('inn') or '—')}\n"
        f"📍 Orienter: {em(data['orienter'])}\n"
        f"📌 Lokatsiya: {em(lokatsiya)}\n"
        f"🏪 Kategoriya: {em(data['kategoriya'])}\n"
        f"🏢 Do'kon turi: {em(data['dokon_turi'])}\n"
        f"🚚 Distributor: {em(data['distributor'])}\n"
        f"👨 Agent/Vizit: {em(data['agent_kod'])}\n"
        f"💰 Limit: {em(str(data['limit']))}\n"
        f"{status_icon} Holat: {em(data['status'])}\n"
    )

    back_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ Ro'yxatga qaytish", callback_data=f"mk_page_{back_page}")
    ]])

    if data.get("rasm"):
        try:
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=data["rasm"])
        except Exception as e:
            logger.warning(f"Klient rasm yuborishda xato: {e}")

    await query.edit_message_text(profile, parse_mode="Markdown", reply_markup=back_kb)


# ══════════════════════════════════════════════
# FORUM TOPIC CLOSED → delete employee + audit
# ══════════════════════════════════════════════

async def topic_closed_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin guruhda topic yopilganda/o'chirilganda xodimni bazadan o'chirib, qayta ro'yxatga yuboradi."""
    msg = update.effective_message
    if not msg or msg.chat.id != GROUP_CHAT_ID:
        return

    topic_id = msg.message_thread_id
    if not topic_id:
        return

    row = await db.get_xodim_by_topic(topic_id)
    if not row:
        return

    user_id, ism = row

    # Audit log: kim, qachon o'chirildi
    await db.insert_audit_log(
        user_id=user_id,
        user_role="xodim",
        action_type="topic_deleted",
        target=ism,
        old_value=f"topic_id={topic_id}",
        new_value=None,
        status="deleted",
    )

    await db.delete_xodim(user_id)
    logger.info(f"Topic #{topic_id} o'chirildi → xodim {ism} ({user_id}) bazadan o'chirildi")

    # Xodimga xabar: qayta ro'yxatdan o'tish kerak
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "⚠️ *Sizning profilingiz administrator tomonidan o'chirildi.*\n\n"
                "Qayta ro'yxatdan o'tish uchun /start bosing."
            ),
            parse_mode="Markdown",
            reply_markup=remove_kb(),
        )
    except Exception as e:
        logger.warning(f"Xodimga xabar yuborishda xato (user_id={user_id}): {e}")
