"""
handlers/klient.py — Klient ro'yxatdan o'tkazish oqimi va admin klient boshqaruvi.
"""
import logging
import re

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import (
    remove_kb, admin_kb, telefon2_kb,
    klient_confirm_kb, klient_edit_fields_kb,
    klient_lokatsiya_inline_kb, klient_kategoriya_kb,
    klient_dokon_turi_kb, klient_chastota_kb,
    klientlar_search_page_inline,
    mening_klientlar_kb,
)
from config import (
    ADMIN_ID,
    DOKON_SLUGLARI,
    AGENT_PREFIX_REGIONS, AGENT_DATABASE,
    KLIENT_RASM, KLIENT_FIRMA_NOMI, KLIENT_TELEFON1, KLIENT_TELEFON2,
    KLIENT_INN, KLIENT_ORIENTER, KLIENT_LOKATSIYA, KLIENT_KATEGORIYA,
    KLIENT_DOKON_TURI, KLIENT_DISTRIBUTOR, KLIENT_AGENT_KOD,
    KLIENT_LIMIT, KLIENT_CONFIRM, KLIENT_EDIT_VALUE,
    KLIENT_CHASTOTA,
    KLIENT_EDIT_LABELS,
)
from handlers._shared import em, format_phone, admin_only, safe_callback_int
from handlers.register import _match_agent_code

logger = logging.getLogger(__name__)


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
    """Klient ma'lumotlari xulasasi — tasdiqlash yoki tahrirlash uchun."""
    lokatsiya = _format_lokatsiya(data)
    vizit = data.get("agent_vizit", "—")
    vizit_kun = data.get("vizit_kun", "")
    agent_line = f"{em(vizit)}" + (f" — {em(vizit_kun)}" if vizit_kun else "")
    summary = (
        f"📋 *Klient ma'lumotlari:*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📸 Rasm: ✅\n"
        f"🏢 Firma: {em(data.get('firma_nomi', '—'))}\n"
        f"📱 Tel 1: {em(data.get('telefon1', '—'))}\n"
        f"📱 Tel 2: {em(data.get('telefon2') or '—')}\n"
        f"🔢 INN: {em(data.get('inn') or '—')}\n"
        f"📍 Orienter: {em(data.get('orienter', '—'))}\n"
        f"📌 Lokatsiya: {em(lokatsiya)}\n"
        f"🗂 Kategoriya: *{em(data.get('kategoriya', '—'))}*\n"
        f"🏪 Do'kon turi: {em(data.get('dokon_turi', '—'))}\n"
        f"👤 Distributor: {em(data.get('distributor', '—'))}\n"
        f"👨 Agent/Vizit: {agent_line}\n"
        f"🔄 Chastota: {em(data.get('chastota') or '—')}\n"
        f"💰 Limit: {em(data.get('limit_text', '—'))}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    await send_fn(text=summary, parse_mode="Markdown", reply_markup=klient_confirm_kb())


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
        "_GPS ulashish yoki manzil yozish usulini tanlang:_",
        parse_mode="Markdown",
        reply_markup=klient_lokatsiya_inline_kb(),
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
        text="🗂 *8-QADAM: Kategoriya* (majburiy)\n\n_Ushbu do'kon uchun kategoriyani tanlang:_",
        parse_mode="Markdown",
        reply_markup=klient_kategoriya_kb(),
    )
    return KLIENT_KATEGORIYA


async def klient_lokatsiya_hint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """lok_gps / lok_text — foydalanuvchiga yo'riqnoma yuboradi."""
    query = update.callback_query
    await query.answer()
    if query.data == "lok_gps":
        await query.message.reply_text(
            "📍 Telegram'dagi 📎 → *Lokatsiya* tugmasini bosib GPS ulashing.",
            parse_mode="Markdown",
        )
    else:
        await query.message.reply_text(
            "✏️ Manzilni matn ko'rinishida yozing.\n_Masalan: 41.2995, 69.2401 yoki ko'cha nomi_",
            parse_mode="Markdown",
        )
    return KLIENT_LOKATSIYA


async def klient_kategoriya(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """8-qadam: kategoriya (A/B/C/D)."""
    query = update.callback_query
    await query.answer()

    kat = query.data[len("klient_kat_"):]
    if kat not in ("A", "B", "C", "D"):
        await query.answer("❌ Noto'g'ri tanlov.", show_alert=True)
        return KLIENT_KATEGORIYA

    context.user_data["klient_data"]["kategoriya"] = kat
    logger.info(f"[KLIENT] Kategoriya selected: {kat}")

    await query.edit_message_text(f"✅ Kategoriya: *{kat}*", parse_mode="Markdown")
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🏪 *9-QADAM: Do'kon turi* (majburiy)",
        parse_mode="Markdown",
        reply_markup=klient_dokon_turi_kb(),
    )
    return KLIENT_DOKON_TURI


async def klient_dokon_turi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """9-qadam: do'kon turi (inline)."""
    query = update.callback_query
    await query.answer()

    slug = query.data[len("klient_tur_"):]
    value = DOKON_SLUGLARI.get(slug)
    if not value:
        await query.answer("❌ Noto'g'ri tanlov.", show_alert=True)
        return KLIENT_DOKON_TURI

    context.user_data["klient_data"]["dokon_turi"] = value
    logger.info(f"[KLIENT] Dokon turi selected: {value}")

    await query.edit_message_text(f"✅ Do'kon turi: *{value}*", parse_mode="Markdown")
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🚚 *10-QADAM: Distributor* (majburiy)\n\n_Distributor nomini kiriting:_",
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
        "👨 *11-QADAM: Agent kodi va Vizit kuni* (majburiy)\n\n"
        "_Agent kodi va vizit kunini birgalikda kiriting._\n"
        "_Masalan: AN001 Dushanba_",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    return KLIENT_AGENT_KOD


async def klient_agent_kod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """11-qadam: agent kodi + vizit kuni — birgalikda kiritiladi."""
    if not update.message or not update.message.text:
        return KLIENT_AGENT_KOD

    parts = update.message.text.strip().split()
    agent_vizit = parts[0].upper()
    vizit_kun = " ".join(parts[1:]).strip() if len(parts) > 1 else ""

    result = _match_agent_code(agent_vizit)
    if not result:
        await update.message.reply_text(
            "❌ Bu agent kodi tizimda mavjud emas.\n"
            "Iltimos, to'g'ri agent kodini kiriting:\n"
            "_Masalan: AN001 Dushanba_",
            parse_mode="Markdown",
        )
        return KLIENT_AGENT_KOD

    _, region = result
    context.user_data["klient_data"]["agent_vizit"] = agent_vizit
    context.user_data["klient_data"]["agent_region"] = region
    context.user_data["klient_data"]["vizit_kun"] = vizit_kun
    logger.info(f"[KLIENT] Agent: {agent_vizit} ({region}), vizit_kun: {vizit_kun!r}")

    await update.message.reply_text(
        f"✅ Agent kodi: *{agent_vizit}* | 📍 {region}"
        + (f"\n📅 Vizit kuni: *{vizit_kun}*" if vizit_kun else ""),
        parse_mode="Markdown",
    )
    await context.bot.send_message(
        chat_id=update.message.chat_id,
        text="🔄 *12-QADAM: Chastota* (majburiy)\n\n_Vizit chastotasini tanlang:_",
        parse_mode="Markdown",
        reply_markup=klient_chastota_kb(),
    )
    return KLIENT_CHASTOTA


async def klient_vizit_kun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """11-qadam: vizit kuni (inline)."""
    query = update.callback_query
    await query.answer()
    from config import VIZIT_KUNLARI
    idx = int(query.data[len("klient_kun_"):])
    kun = VIZIT_KUNLARI[idx]
    context.user_data["klient_data"]["vizit_kun"] = kun
    await query.edit_message_text(f"✅ Vizit kuni: *{kun}*", parse_mode="Markdown")
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🔄 *12-QADAM: Chastota* (majburiy)\n\n_Vizit chastotasini tanlang:_",
        parse_mode="Markdown",
        reply_markup=klient_chastota_kb(),
    )
    return KLIENT_CHASTOTA


async def klient_chastota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """12-qadam: chastota (inline)."""
    query = update.callback_query
    await query.answer()
    from config import CHASTOTA_LIST
    idx = int(query.data[len("klient_chas_"):])
    chastota = CHASTOTA_LIST[idx]
    context.user_data["klient_data"]["chastota"] = chastota
    await query.edit_message_text(f"✅ Chastota: *{chastota}*", parse_mode="Markdown")
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="💰 *13-QADAM: Limit* (majburiy)\n\n"
             "_Har loyiha uchun limitni yozing. Masalan:_\n"
             "```\nCable: 1,000,000\nDusel: 500,000\nTools: 800,000\n```",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    return KLIENT_LIMIT


async def klient_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """13-qadam: limit - free text."""
    if not update.message or not update.message.text:
        return KLIENT_LIMIT

    limit_text = update.message.text.strip()
    if not limit_text:
        await update.message.reply_text("❌ Limit bo'sh bo'lmasligi kerak.")
        return KLIENT_LIMIT

    context.user_data["klient_data"]["limit_text"] = limit_text
    logger.info(f"[KLIENT] Limit accepted: {limit_text[:50]}")

    await _show_klient_summary(
        lambda **kw: update.message.reply_text(**kw),
        context.user_data["klient_data"],
    )
    return KLIENT_CONFIRM


async def klient_brendlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """14-qadam: brendlar multi-select (inline)."""
    query = update.callback_query
    await query.answer()

    if query.data == "klient_brands_confirm":
        selected = context.user_data["klient_data"].get("brendlar_selected", [])
        from config import BRENDLAR_LIST
        brendlar_str = ", ".join(BRENDLAR_LIST[i] for i in sorted(selected)) if selected else ""
        context.user_data["klient_data"]["brendlar"] = brendlar_str
        await query.edit_message_text(
            f"✅ Brendlar: *{brendlar_str or 'Tanlanmagan'}*", parse_mode="Markdown"
        )
        await _show_klient_summary(
            lambda **kw: context.bot.send_message(chat_id=query.message.chat_id, **kw),
            context.user_data["klient_data"],
        )
        return KLIENT_CONFIRM

    idx = int(query.data[len("klient_brand_"):])
    selected = context.user_data["klient_data"].setdefault("brendlar_selected", [])
    if idx in selected:
        selected.remove(idx)
    else:
        selected.append(idx)
    from keyboards import klient_brendlar_kb_selected
    await query.edit_message_reply_markup(reply_markup=klient_brendlar_kb_selected(selected))
    from config import KLIENT_BRENDLAR
    return KLIENT_BRENDLAR


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
                vizit_kun=data.get("vizit_kun", ""),
                chastota=data.get("chastota", ""),
                limit_summa=data.get("limit_text"),
                brendlar=data.get("brendlar", ""),
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

            vizit_line = data.get("agent_vizit", "—")
            if data.get("vizit_kun"):
                vizit_line += f" — {data['vizit_kun']}"
            admin_card = (
                f"📋 *Yangi Klient #{klient_id}*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏢 Firma: {em(data.get('firma_nomi', '—'))}\n"
                f"📱 Tel 1: {em(data.get('telefon1', '—'))}\n"
                f"📱 Tel 2: {em(data.get('telefon2') or '—')}\n"
                f"🔢 INN: {em(data.get('inn') or '—')}\n"
                f"📍 Orienter: {em(data.get('orienter', '—'))}\n"
                f"📌 Lokatsiya: {em(lokatsiya)}\n"
                f"🗂 Kategoriya: *{em(data.get('kategoriya', '—'))}*\n"
                f"🏪 Do'kon turi: {em(data.get('dokon_turi', '—'))}\n"
                f"👤 Distributor: {em(data.get('distributor', '—'))}\n"
                f"👨 Agent/Vizit: {em(vizit_line)}\n"
                f"🔄 Chastota: {em(data.get('chastota') or '—')}\n"
                f"💰 Limit: {em(data.get('limit_text', '—'))}\n"
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

            from config import GROUP_CHAT_ID
            # General topic (message_thread_id=1) ga to'liq klient kartasi
            group_card = (
                f"🏪 *Yangi Klient #{klient_id}*\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🏢 {em(data.get('firma_nomi', '—'))}\n"
                f"📱 {em(data.get('telefon1', '—'))}\n"
                f"📍 {em(data.get('orienter', '—'))}\n"
                f"📌 {em(lokatsiya)}\n"
                f"🗂 Kategoriya: *{em(data.get('kategoriya', '—'))}*\n"
                f"🏪 {em(data.get('dokon_turi', '—'))}\n"
                f"👤 Distributor: {em(data.get('distributor', '—'))}\n"
                f"👨 Agent/Vizit: {em(vizit_line)}\n"
                f"💰 Limit: {em(data.get('limit_text', '—'))}\n"
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

    elif query.data == "klient_edit":
        await query.edit_message_reply_markup(reply_markup=klient_edit_fields_kb())
        return KLIENT_CONFIRM

    elif query.data == "klient_edit_back":
        await query.edit_message_reply_markup(reply_markup=klient_confirm_kb())
        return KLIENT_CONFIRM

    elif query.data.startswith("klient_ef_"):
        field_key = query.data[len("klient_ef_"):]
        label = KLIENT_EDIT_LABELS.get(field_key, field_key)
        current = context.user_data.get("klient_data", {}).get(field_key, "")
        context.user_data["klient_edit_key"] = field_key
        await query.message.reply_text(
            f"✏️ *{em(label)}* ni tahrirlash\n\n"
            f"Hozirgi qiymat: `{em(str(current) if current else '—')}`\n\n"
            "_Yangi qiymatni kiriting:_",
            parse_mode="Markdown",
        )
        return KLIENT_EDIT_VALUE

    return KLIENT_CONFIRM


async def klient_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Edit: foydalanuvchi yangi qiymat kiritadi, saqlaydi va xulosani qayta ko'rsatadi."""
    field_key = context.user_data.pop("klient_edit_key", None)
    if not field_key or not update.message or not update.message.text:
        return KLIENT_CONFIRM

    new_value = update.message.text.strip()
    context.user_data["klient_data"][field_key] = new_value
    label = KLIENT_EDIT_LABELS.get(field_key, field_key)
    logger.info(f"[KLIENT] Edit: {field_key} = {new_value[:50]!r}")

    await update.message.reply_text(f"✅ *{em(label)}* yangilandi.", parse_mode="Markdown")
    await _show_klient_summary(
        lambda **kw: update.message.reply_text(**kw),
        context.user_data["klient_data"],
    )
    return KLIENT_CONFIRM


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
    """Klientni rad etish, klient qidirish, sorov javobini yuborish va admin private reply."""
    if not await db.is_admin(update.effective_user.id):
        return

    msg = update.message
    if not msg:
        return

    # Admin private chatda xodim notifikatsiyasiga reply → xodimga yo'naltirish
    if msg.reply_to_message:
        replied_id = msg.reply_to_message.message_id
        notif_map = context.bot_data.get("admin_notif_map", {})
        if replied_id in notif_map:
            group_id, emp_uid = notif_map[replied_id]
            try:
                await msg.copy(chat_id=emp_uid)
                await msg.reply_text(f"✅ #{group_id} xodimga yuborildi.")
            except Exception as e:
                logger.warning(f"Admin private reply xodimga yuborishda xato: {e}")
            return

    # Matn bo'lmasa quyidagi logikani o'tkazib yuboramiz
    if not msg.text:
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
