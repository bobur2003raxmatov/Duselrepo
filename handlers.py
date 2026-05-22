import logging
import os
from datetime import datetime
from functools import wraps

from telegram import Update, BotCommand, ReplyParameters
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler
from telegram.helpers import escape_markdown

import database as db
from keyboards import (
    lavozim_kb, filial_kb, telefon_kb, telefon2_kb, remove_kb,
    admin_kb, edit_field_kb, edit_select_kb, xodimlar_page_inline,
    sorov_inline, bajarildi_inline, tasdiq_inline, unblock_inline,
    group_sorov_inline, group_bajarildi_inline,
    search_results_kb, xodim_profil_kb,
    biriktirish_list_kb, biriktir_detail_kb,
    biriktirish_agents_kb, biriktirish_checkers_kb, checker_sorov_kb,
    urgency_kb, stars_kb, filial_filter_kb,
)
from utils import (
    is_topic_valid, check_sla_timeout, generate_excel,
    urgency_timeout_job, checker_timeout_job,
)
from config import (
    ADMIN_ID, GROUP_CHAT_ID, FILIALLAR, LAVOZIMLAR,
    SLA_TIMEOUT_SEC, GROUP_TIMEOUT_SEC, PAGE_SIZE,
    URGENCY_TIMEOUT_SEC, CHECKER_TIMEOUT_SEC,
    ISM, LAVOZIM, KOD, FILIAL, TELEFON, TELEFON2, TUGILGAN_KUN,
    EDIT_USER, EDIT_FIELD, EDIT_VALUE, SEARCH_QUERY,
    BIRIKTIR_AGENT, BIRIKTIR_CHECKER, BIRIKTIR_DETAIL,
    BIRIKTIR_EDIT_FIELD, BIRIKTIR_EDIT_VALUE,
)

logger = logging.getLogger(__name__)


def em(text) -> str:
    """Markdown v1 uchun foydalanuvchi matnini xavfsiz qiladi."""
    return escape_markdown(str(text), version=1)


def _schedule_sla(context, group_id: int, ism: str):
    """15 va 30 daqiqali SLA eslatmalarini rejalashtiradi."""
    context.job_queue.run_once(
        check_sla_timeout,
        when=SLA_TIMEOUT_SEC,
        data={"group_id": group_id, "x_ism": ism, "reminder": 1},
    )
    context.job_queue.run_once(
        check_sla_timeout,
        when=SLA_TIMEOUT_SEC * 2,
        data={"group_id": group_id, "x_ism": ism, "reminder": 2},
    )


def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
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
    uid = update.effective_user.id

    if uid == ADMIN_ID:
        await update.message.reply_text(
            "👑 *Admin boshqaruv paneliga xush kelibsiz!*",
            parse_mode="Markdown",
            reply_markup=admin_kb(),
        )
        return ConversationHandler.END

    user = await db.get_xodim(uid)
    if user:
        status, topic_id, ism, *_ = user

        if status == "blocked":
            await update.message.reply_text("❌ Profilingiz ma'muriyat tomonidan bloklangan.")
            return ConversationHandler.END

        if status == "approved":
            topic_ok = await is_topic_valid(context, topic_id)
            if not topic_ok:
                await db.delete_xodim(uid)
                await update.message.reply_text(
                    "⚠️ Sizga tegishli guruhdagi mavzu (Topic) o'chirilgan.\n"
                    "Iltimos, qaytadan ro'yxatdan o'ting:\n\n"
                    "*Ism va Familiyangizni* kiriting:",
                    parse_mode="Markdown",
                    reply_markup=remove_kb(),
                )
                return ISM
            await update.message.reply_text(
                f"✅ Tizim faol, {em(ism)}!\n"
                "Istalgan topshiriq yoki hisobotingizni to'g'ridan-to'g'ri yuboring.",
                parse_mode="Markdown",
                reply_markup=remove_kb(),
            )
            return ConversationHandler.END

        await update.message.reply_text(
            "⏳ Profilingiz admin tomonidan tasdiqlanish jarayonida.",
            reply_markup=remove_kb(),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Assalomu Alaykum! Dusel Company botiga xush kelibsiz. 👋\n\n"
        "Iltimos, *Ism va Familiyangizni* kiriting:",
        parse_mode="Markdown",
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


async def kod_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["kod"] = update.message.text.strip().upper()
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
    if not update.message.contact:
        await update.message.reply_text(
            "❌ Iltimos, raqam yuborish tugmasini bosing:",
            reply_markup=telefon_kb(),
        )
        return TELEFON
    context.user_data["telefon1"] = update.message.contact.phone_number
    await update.message.reply_text(
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
            f"👤 Ism: {d['ism']}\n"
            f"💼 Lavozim: {d['lavozim']}\n"
            f"🔑 Kod: `{d['kod']}`\n"
            f"🏢 Viloyat: {d['filial']}\n"
            f"📱 Tel 1: {d['telefon1']}\n"
            f"📱 Tel 2: {d['telefon2']}\n"
            f"🎂 Tug'ilgan kun: {tkun}\n"
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
    if not msg or msg.chat.id == GROUP_CHAT_ID or update.effective_user.id == ADMIN_ID:
        return

    uid  = update.effective_user.id
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

    if msg.photo:        ctype = "📷 Rasm"
    elif msg.video:      ctype = "🎥 Video"
    elif msg.document:   ctype = "📄 Fayl"
    elif msg.voice:      ctype = "🎙 Ovozli xabar"
    elif msg.video_note: ctype = "⭕ Video-xabar"
    elif msg.sticker:    ctype = "🎭 Sticker"
    else:                ctype = "💬 Matn"

    # Reply konteksti (admin xabariga reply qilyaptimi?)
    reply_to_group_id = None
    if msg.reply_to_message:
        reply_to_group_id = await db.get_group_msg_id_by_private(uid, msg.reply_to_message.message_id)

    # Aktiv guruh bor-yo'qligini tekshirish (oxirgi 60 soniya)
    active = await db.get_active_group(uid)

    async def _fwd(t_id: int):
        if reply_to_group_id:
            try:
                return await context.bot.copy_message(
                    chat_id=GROUP_CHAT_ID,
                    from_chat_id=msg.chat_id,
                    message_id=msg.message_id,
                    message_thread_id=t_id,
                    reply_parameters=ReplyParameters(message_id=reply_to_group_id),
                )
            except BadRequest:
                pass
        return await msg.forward(chat_id=GROUP_CHAT_ID, message_thread_id=t_id)

    async def _log(group_id: int):
        """General topicga sukut bilan log yozadi (faqat admin uchun)."""
        role_txt   = f"{lavozim} ({kod})" if kod and kod != "KOD YO'Q" else lavozim
        topic_name = f"{ism} — {role_txt} | {filial}"
        now_str    = datetime.now().strftime("%d.%m %H:%M")
        if msg.text:
            content = msg.text[:100] + ("..." if len(msg.text) > 100 else "")
        else:
            content = ctype
        log_text = f"[{topic_name}] {ism}: {content} — {now_str}"
        try:
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=log_text,
                disable_notification=True,   # sukut — hech qanday signal yo'q
                protect_content=True,        # forward/screenshot oldini oladi
            )
        except Exception as e:
            logger.warning(f"General topicga log yuborishda xato: {e}")

    if active:
        # ── Mavjud guruhga qo'shish ──────────────────────────────
        group_id, _ = active
        task_id = await db.insert_xabar(uid, ism, filial, ctype, msg.message_id, group_id)
        msg_count = await db.count_group_msgs(group_id)

        try:
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic_id,
                text=f"➕ *{ism}* — {ctype} ({msg_count}-xabar, guruh #{group_id})",
                parse_mode="Markdown",
            )
            fwd = await _fwd(topic_id)
            await db.update_xabar_group_fwd_id(task_id, fwd.message_id)
            await _log(group_id)
            await msg.reply_text(f"✅ #{group_id}-guruhga qo'shildi ({msg_count}-xabar).")

        except BadRequest as e:
            if "message thread not found" in str(e).lower():
                await db.reset_topic(uid)
                await msg.reply_text(
                    "⚠️ Guruhdagi kanalingiz o'chirilgan. Qayta tasdiqlash kutilmoqda."
                )
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"🔄 *Mavzusi o'chirilgan xodim:*\n\n"
                        f"👤 {ism} | {lavozim}"
                    ),
                    parse_mode="Markdown",
                    reply_markup=tasdiq_inline(uid),
                )
            else:
                logger.error(f"Guruhga qo'shishda xato (uid={uid}): {e}")
                await msg.reply_text("❌ Xato yuz berdi. Qayta urinib ko'ring.")
        except Exception as e:
            logger.error(f"Guruhga qo'shishda xato (uid={uid}): {e}")
            await msg.reply_text("❌ Xato yuz berdi. Qayta urinib ko'ring.")

    else:
        # ── Yangi guruh ochish ───────────────────────────────────
        group_id = await db.create_xabar_guruhi(uid, ism, filial, topic_id)
        task_id  = await db.insert_xabar(uid, ism, filial, ctype, msg.message_id, group_id)

        try:
            now_hm = datetime.now().strftime("%H:%M")
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic_id,
                text=(
                    f"📨 *Xodim:* {ism}  |  Guruh #{group_id}\n"
                    f"🕒 *Vaqt:* {now_hm}  |  {ctype}"
                ),
                parse_mode="Markdown",
            )
            fwd = await _fwd(topic_id)
            await db.update_xabar_group_fwd_id(task_id, fwd.message_id)
            await _log(group_id)
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic_id,
                text=f"#{group_id}-guruh holati:",
                reply_markup=group_sorov_inline(group_id),
            )
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"📬 *Yangi topshiriq!*\n"
                    f"👤 Xodim: {ism}  |  🔢 #{group_id}"
                ),
                parse_mode="Markdown",
                reply_markup=group_sorov_inline(group_id),
            )
            await msg.reply_text(
                f"✅ #{group_id}-sonli so'rovingiz qabul qilindi. Admin javobini kuting."
            )

            # Biriktirish: Agent bo'lsa checker borligini tekshir
            checker_id = await db.get_biriktirish(uid) if lavozim == "Agent" else None

            if checker_id:
                # Urgency tanlash so'rash — checker xabari urgency tanlanganida ketadi
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=f"#{group_id} topshiriqning muhimlilik darajasini tanlang:",
                        reply_markup=urgency_kb(group_id),
                        disable_notification=True,
                    )
                except Exception:
                    pass
                # 60 soniyada urgency tanlanmasa — oddiy deb checker ga yuborish
                context.job_queue.run_once(
                    urgency_timeout_job,
                    when=URGENCY_TIMEOUT_SEC,
                    data={"group_id": group_id, "checker_id": checker_id, "ism": ism},
                    name=f"urgency_{group_id}",
                )
                # Checker timeout (30 daqiqada javob bermasa admin ogohlantiriladi)
                context.job_queue.run_once(
                    checker_timeout_job,
                    when=CHECKER_TIMEOUT_SEC,
                    data={"group_id": group_id, "ism": ism},
                )
            else:
                _schedule_sla(context, group_id, ism)
                # Feature 10: Checker yo'q bo'lsa adminga maxsus xabar
                if lavozim == "Agent":
                    try:
                        await context.bot.send_message(
                            chat_id=ADMIN_ID,
                            text=(
                                f"⚠️ *{em(ism)}* uchun checker biriktirilmagan!\n"
                                f"'🔗 Biriktirish' menyusidan biriktiring."
                            ),
                            parse_mode="Markdown",
                        )
                    except Exception:
                        pass

        except BadRequest as e:
            if "message thread not found" in str(e).lower():
                await db.reset_topic(uid)
                await msg.reply_text(
                    "⚠️ Guruhdagi kanalingiz o'chirilgan. Qayta tasdiqlash kutilmoqda."
                )
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"🔄 *Mavzusi o'chirilgan xodim:*\n\n"
                        f"👤 {ism} | {lavozim}"
                    ),
                    parse_mode="Markdown",
                    reply_markup=tasdiq_inline(uid),
                )
            else:
                logger.error(f"Yangi guruh ochishda xato (uid={uid}): {e}")
                await msg.reply_text("❌ Xato yuz berdi. Qayta urinib ko'ring.")
        except Exception as e:
            logger.error(f"Yangi guruh ochishda xato (uid={uid}): {e}")
            await msg.reply_text("❌ Xato yuz berdi. Qayta urinib ko'ring.")


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
            )
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
        # Feature 11: checker ga xabar
        row = await db.get_xodim(target_uid)
        if row and row[3] == "Agent":
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
        # Feature 11: checker ga xabar
        row = await db.get_xodim(target_uid)
        if row and row[3] == "Agent":
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


async def _cb_xod_page(query, page: int):
    rows = await db.get_approved_xodimlar()
    if not rows:
        await query.edit_message_text("👥 Tizimda faol xodimlar hozircha yo'q.")
        return
    total = len(rows)
    start = page * PAGE_SIZE
    end   = min(start + PAGE_SIZE, total)
    matn  = f"👥 *Faol xodimlar ({start + 1}–{end} / {total}):*\n\n"
    for r in rows[start:end]:
        matn += f"👤 *{em(r[0])}* | {em(r[1])} | Kod: `{em(r[3])}` | ID: `{r[4]}`\n"
    await query.edit_message_text(matn, parse_mode="Markdown", reply_markup=xodimlar_page_inline(page, total))


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
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🔄 #{group_id}-sonli so'rovingiz ko'rib chiqilmoqda.",
            )
        except Exception as e:
            logger.warning(f"Guruh jarayon xabari yuborishda xato: {e}")

    elif action == "done":
        await db.update_group_holat(group_id, "bajarildi")
        main_msg = await db.get_most_important_msg(group_id)
        await query.edit_message_text(f"✅ #{group_id}-guruh yakunlandi!")
        try:
            rp = ReplyParameters(message_id=main_msg[2]) if main_msg else None
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ #{group_id}-sonli so'rovingiz bajarildi!",
                reply_parameters=rp,
            )
        except Exception as e:
            logger.warning(f"Guruh bajarildi xabari yuborishda xato: {e}")


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
        parts    = data.split("_")
        group_id = int(parts[1])
        level    = parts[2]
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

    # ── Yulduz reyting (checker tomonidan) ────────────────────────
    if data.startswith("star_"):
        parts    = data.split("_")
        group_id = int(parts[1])
        yulduz   = int(parts[2])
        checker  = query.from_user.id
        group    = await db.get_group_info(group_id)
        if not group:
            await query.edit_message_text("❌ Guruh topilmadi.")
            return
        agent_uid = group[0]
        await db.add_baholash(group_id, checker, agent_uid, yulduz)
        await db.update_checker_faollik(checker)
        stars_str = "⭐" * yulduz
        await query.edit_message_text(f"✅ #{group_id} — {stars_str} bilan baholandi!")
        try:
            summary = await db.get_agent_rating_summary(agent_uid)
            await context.bot.send_message(
                chat_id=agent_uid,
                text=(
                    f"⭐ #{group_id} topshiriqingiz *{stars_str}* bilan baholandi!\n"
                    f"Sizning o'rtacha reytingingiz: *{summary['avg']}* ({summary['total']} ta baho)"
                ),
                parse_mode="Markdown",
            )
        except Exception:
            pass
        return

    # ── Checker callback (admin bo'lmagan xodimlar uchun) ─────────
    if data.startswith("bir_tasd_"):
        group_id  = int(data.split("_")[2])
        checker   = query.from_user.id
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
        await query.edit_message_text(f"✅ #{group_id} topshiriqni tasdiqladingiz!")
        # Feature 17: Baholash so'rash
        try:
            await context.bot.send_message(
                chat_id=checker,
                text=f"#{group_id} topshiriqni baholang (1-5 yulduz):",
                reply_markup=stars_kb(group_id),
            )
        except Exception:
            pass
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
        group_id  = int(data.split("_")[2])
        checker   = query.from_user.id
        group     = await db.get_group_info(group_id)
        if not group:
            await query.edit_message_text("❌ Topshiriq topilmadi.")
            return
        agent_uid, agent_ism = group[0], group[1]
        if await db.get_biriktirish(agent_uid) != checker:
            await query.answer("Siz bu topshiriqni rad etish huquqiga ega emassiz.", show_alert=True)
            return
        await db.update_checker_faollik(checker)
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

    if data.startswith("filial_lider_"):
        period = data.split("_")[2]
        await _send_filial_leaderboard(query.edit_message_text, period)
        return

    if data.startswith("xodim_profil_"):
        uid = int(data.split("_")[2])
        row = await db.get_xodim_full(uid)
        if not row:
            await query.edit_message_text("❌ Xodim topilmadi.")
            return
        await query.edit_message_text(
            _format_profil(row),
            parse_mode="Markdown",
            reply_markup=xodim_profil_kb(uid, row[9]),
        )
        return

    if data.startswith(("appr_", "reje_", "block_", "unbl_")):
        action, uid = data.split("_", 1)[0], int(data.split("_", 1)[1])
        await _cb_user_action(query, context, action, uid)

    elif data.startswith("xod_page_"):
        await _cb_xod_page(query, int(data.split("_")[2]))

    elif data.startswith(("grp_prog_", "grp_done_")):
        parts = data.split("_")
        await _cb_group_action(query, context, parts[1], int(parts[2]))

    elif data.startswith(("prog_", "done_")):
        action, task_id = data.split("_", 1)[0], int(data.split("_", 1)[1])
        await _cb_task_action(query, context, action, task_id)


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


async def _send_xodimlar_page(send_fn, rows: list, page: int):
    total = len(rows)
    start = page * PAGE_SIZE
    end   = min(start + PAGE_SIZE, total)
    matn  = f"👥 *Faol xodimlar ({start + 1}–{end} / {total}):*\n\n"
    for r in rows[start:end]:
        matn += f"👤 *{r[0]}* | {r[1]} | Kod: `{r[3]}` | ID: `{r[4]}`\n"
    await send_fn(matn, parse_mode="Markdown", reply_markup=xodimlar_page_inline(page, total))


@admin_only
async def admin_xodimlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await db.get_approved_xodimlar()
    if not rows:
        await update.message.reply_text("👥 Tizimda faol xodimlar hozircha yo'q.")
        return
    await _send_xodimlar_page(update.message.reply_text, rows, page=0)


@admin_only
async def admin_kutilayotganlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await db.get_pending_xodimlar()
    if not rows:
        await update.message.reply_text("✅ Kutilayotgan arizalar yo'q.")
        return
    for u in rows:
        await update.message.reply_text(
            f"⏳ *Kutilayotgan ariza:* {u[1]} ({u[2]})\n"
            f"🔑 Kod: `{u[3]}`  |  🏢 Filial: {u[4]}",
            parse_mode="Markdown",
            reply_markup=tasdiq_inline(u[0]),
        )


@admin_only
async def admin_bloklanganlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await db.get_blocked_xodimlar()
    if not rows:
        await update.message.reply_text("🚫 Bloklanganlar mavjud emas.")
        return
    for r in rows:
        await update.message.reply_text(
            f"🚫 *Bloklangan:* {r[1]}\n🔑 Kod: `{r[4]}`",
            parse_mode="Markdown",
            reply_markup=unblock_inline(r[0]),
        )


@admin_only
async def admin_excel_eksport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📥 Excel hisoboti tayyorlanmoqda...")
    x_data   = await db.get_all_xodimlar_for_excel()
    m_data   = await db.get_all_xabarlar_for_excel()
    filename = await generate_excel(x_data, m_data)
    with open(filename, "rb") as f:
        await update.message.reply_document(
            document=f,
            caption="📈 Dusel Company tizimining batafsil Excel hisoboti.",
            filename=filename,
        )
    os.remove(filename)


# ══════════════════════════════════════════════
# XODIMNI TAHRIRLASH OQIMI (ADMIN)
# ══════════════════════════════════════════════
@admin_only
async def start_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await db.get_approved_xodimlar()
    if not rows:
        await update.message.reply_text("👥 Tahrirlash uchun faol xodimlar yo'q.", reply_markup=admin_kb())
        return ConversationHandler.END
    context.user_data["edit_rows"] = rows
    await update.message.reply_text(
        f"📝 Xodimni tanlang yoki ismini yozing:\n_(Jami: {len(rows)} ta xodim)_",
        parse_mode="Markdown",
        reply_markup=edit_select_kb(rows, page=0),
    )
    return EDIT_USER


async def edit_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split("_")[2])
    rows = context.user_data.get("edit_rows") or await db.get_approved_xodimlar()
    context.user_data["edit_rows"] = rows
    await query.edit_message_reply_markup(reply_markup=edit_select_kb(rows, page))
    return EDIT_USER


async def edit_select_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_uid = int(query.data.split("_")[2])

    row = await db.get_xodim(target_uid)
    if not row:
        await query.edit_message_text("❌ Xodim topilmadi.")
        return ConversationHandler.END

    _, _, ism, lavozim, filial, _ = row
    context.user_data["edit_uid"] = target_uid

    await query.edit_message_text(
        f"✅ *{ism}* ({lavozim} | {filial}) tanlandi.",
        parse_mode="Markdown",
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Qaysi ma'lumotni o'zgartirmoqchisiz?",
        reply_markup=edit_field_kb(),
    )
    return EDIT_FIELD


async def edit_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    search_text = update.message.text.strip()
    rows = await db.search_xodimlar(search_text)

    if not rows:
        await update.message.reply_text(
            f"❌ *'{search_text}'* bo'yicha xodim topilmadi. Qayta kiriting:",
            parse_mode="Markdown",
        )
        return EDIT_USER

    context.user_data["edit_rows"] = rows
    await update.message.reply_text(
        f"🔍 *{len(rows)} ta* natija topildi. Birini tanlang:",
        parse_mode="Markdown",
        reply_markup=edit_select_kb(rows, page=0),
    )
    return EDIT_USER


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
@admin_only
async def admin_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 Xodimning *ismi* yoki *Telegram ID* sini kiriting:",
        parse_mode="Markdown",
        reply_markup=remove_kb(),
    )
    return SEARCH_QUERY


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
    rating = await db.get_agent_rating_summary(agent_id)
    STATUS_TEXT = {"approved": "✅ Faol", "pending": "⏳ Kutilmoqda", "blocked": "🚫 Bloklangan"}

    matn = (
        f"👤 *{em(ism)}*\n"
        f"💼 {em(lavozim)} | 🔑 `{em(kod)}` | 🏢 {em(filial)}\n"
        f"📱 {em(tel1 or '—')} | 🆔 `{uid}` | {STATUS_TEXT.get(status,'?')}\n\n"
        f"🔗 Checker: {checker_ism or '—'}\n\n"
        f"📊 Bugun: *{stats['bugun']}* ta | ✅ *{stats['bajarildi']}* bajarildi\n"
        f"⭐ Reyting: *{rating['avg']}* ({rating['total']} baho) | Bu hafta: *{rating['haftalik'] or '—'}*"
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
    agent_id = int(query.data.split("_")[2])
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
    agent_id = int(query.data.split("_")[2])
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
    agent_id = int(query.data.split("_")[2])
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
    agent_id = int(query.data.split("_")[2])
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


# ══════════════════════════════════════════════
# REYTING VA FILIAL LEADERBOARD (Features 17, 19)
# ══════════════════════════════════════════════
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


async def _send_filial_leaderboard(send_fn, period: str = "haftalik"):
    rows = await db.get_filial_stats(period)
    PERIOD_LABEL = {"haftalik": "Haftalik", "oylik": "Oylik", "yillik": "Yillik", "hammasi": "Jami"}
    label = PERIOD_LABEL.get(period, period)
    matn = f"🏆 *Filial Reytingi — {label}*\n\n"
    if not rows:
        matn += "_Ma'lumot yo'q._"
    else:
        for i, r in enumerate(rows, 1):
            filial, agents, topshiriq, bajarildi, avg_r, avg_vaqt = r
            medal = MEDALS.get(i, f"{i}.")
            stars = ("⭐" * round(avg_r)) if avg_r else "—"
            vaqt_str = f"{avg_vaqt:.0f} daq" if avg_vaqt else "—"
            matn += (
                f"{medal} *{em(filial or '?')}*\n"
                f"   👥 Agentlar: {agents}  |  📋 Topshiriq: {topshiriq or 0}\n"
                f"   ✅ Bajarildi: {bajarildi or 0}  |  ⭐ {stars}  |  ⏱ {vaqt_str}\n\n"
            )
    await send_fn(
        matn,
        parse_mode="Markdown",
        reply_markup=filial_filter_kb(period),
    )


@admin_only
async def admin_filial_lider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_filial_leaderboard(update.message.reply_text, "haftalik")


@admin_only
async def admin_agent_reyting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await db.get_agent_leaderboard()
    matn = "⭐ *Agent Reytingi*\n\n"
    if not rows:
        matn += "_Hali hech qanday baho yo'q._"
    else:
        for i, r in enumerate(rows, 1):
            uid, ism, filial, avg, total, haftalik = r
            medal = MEDALS.get(i, f"#{i}")
            haftalik_str = f"{haftalik}" if haftalik else "—"
            matn += (
                f"{medal} *{em(ism)}* | {em(filial)}\n"
                f"   Umumiy: {'⭐' * round(avg)} *{avg}* ({total} baho)"
                f"  |  Bu hafta: {haftalik_str}\n\n"
            )
    await update.message.reply_text(matn, parse_mode="Markdown", reply_markup=admin_kb())
