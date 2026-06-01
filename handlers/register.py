"""
handlers/register.py — /start va ro'yxatdan o'tish oqimi.
"""
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import (
    lavozim_kb, filial_kb, telefon_kb, telefon2_kb, remove_kb,
    admin_kb, tasdiq_inline,
)
from config import (
    FILIALLAR, LAVOZIMLAR,
    ISM, LAVOZIM, KOD, FILIAL, TELEFON, TELEFON2, TUGILGAN_KUN,
    AGENT_PREFIX_REGIONS, AGENT_DATABASE,
)
from handlers._shared import (
    em, format_phone, _role_keyboard,
)


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
    from config import ADMIN_ID as _ADMIN_ID
    await context.bot.send_message(
        chat_id=_ADMIN_ID,
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
