import logging
import os
from datetime import datetime
from functools import wraps

from telegram import Update, BotCommand
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import (
    lavozim_kb, filial_kb, telefon_kb, telefon2_kb, remove_kb,
    admin_kb, edit_field_kb, edit_select_kb, xodimlar_page_inline,
    sorov_inline, bajarildi_inline, tasdiq_inline, unblock_inline,
)
from utils import is_topic_valid, check_sla_timeout, generate_excel
from config import (
    ADMIN_ID, GROUP_CHAT_ID, FILIALLAR, LAVOZIMLAR, SLA_TIMEOUT_SEC, PAGE_SIZE,
    ISM, LAVOZIM, KOD, FILIAL, TELEFON, TELEFON2, TUGILGAN_KUN,
    EDIT_USER, EDIT_FIELD, EDIT_VALUE, SEARCH_QUERY,
)

logger = logging.getLogger(__name__)


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
    await context.bot.set_my_commands([
        BotCommand("start",  "Botni qayta ishga tushirish"),
        BotCommand("cancel", "Jarayonni bekor qilish"),
    ])

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
                f"✅ Tizim faol, {ism}!\n"
                "Istalgan topshiriq yoki hisobotingizni to'g'ridan-to'g'ri yuboring.",
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

    task_id = await db.insert_xabar(uid, ism, filial, ctype, msg.message_id)

    try:
        now_hm = datetime.now().strftime("%H:%M")
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            message_thread_id=topic_id,
            text=(
                f"📨 *Xodim:* {ism}  |  #{task_id}\n"
                f"🕒 *Tushgan Vaqt:* {now_hm}  |  {ctype}"
            ),
            parse_mode="Markdown",
        )
        await msg.forward(chat_id=GROUP_CHAT_ID, message_thread_id=topic_id)
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            message_thread_id=topic_id,
            text=f"#{task_id}-sonli xabar holati:",
            reply_markup=sorov_inline(task_id),
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"📬 *Yangi topshiriq!*\n"
                f"👤 Xodim: {ism}  |  🔢 #{task_id}\n"
                f"⏳ _15 daqiqalik nazorat boshlandi!_"
            ),
            parse_mode="Markdown",
            reply_markup=sorov_inline(task_id),
        )
        await msg.reply_text(
            f"✅ #{task_id}-sonli so'rovingiz qabul qilindi. Admin javobini kuting."
        )
        context.job_queue.run_once(
            check_sla_timeout,
            when=SLA_TIMEOUT_SEC,
            data={"task_id": task_id, "topic_id": topic_id, "x_ism": ism, "reminder": 1},
        )
        context.job_queue.run_once(
            check_sla_timeout,
            when=SLA_TIMEOUT_SEC * 2,
            data={"task_id": task_id, "topic_id": topic_id, "x_ism": ism, "reminder": 2},
        )

    except BadRequest as e:
        if "message thread not found" in str(e).lower():
            await db.reset_topic(uid)
            await msg.reply_text(
                "⚠️ Guruhdagi sizning kanalingiz (Topic) o'chirib tashlangan!\n"
                "Profilingiz qayta tasdiqlash holatiga o'tkazildi, admin ruxsatini kuting."
            )
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🔄 *Mavzusi o'chirilgan xodim aniqlandi:*\n\n"
                    f"👤 Xodim: {ism} | {lavozim}\n"
                    f"Tizim uni avtomatik qayta tasdiqlash ro'yxatiga soldi."
                ),
                parse_mode="Markdown",
                reply_markup=tasdiq_inline(uid),
            )
        else:
            logger.error(f"Xabar uzatishda xato (uid={uid}): {e}")
            await msg.reply_text("❌ Xabar yuborishda xato yuz berdi. Iltimos qayta urinib ko'ring.")
    except Exception as e:
        logger.error(f"Xabar uzatishda xato (uid={uid}): {e}")
        await msg.reply_text("❌ Xabar yuborishda xato yuz berdi. Iltimos qayta urinib ko'ring.")


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
    try:
        await msg.copy(chat_id=user_id)
    except Exception as e:
        logger.error(f"Admin javobini xodimga yuborishda xato (uid={user_id}): {e}")


# ══════════════════════════════════════════════
# CALLBACK HANDLER
# ══════════════════════════════════════════════
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    # ── Xodim tasdiqlash / bloklash ───────────────────────────────
    if data.startswith(("appr_", "reje_", "block_", "unbl_")):
        action, target_uid = data.split("_", 1)[0], int(data.split("_", 1)[1])

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
                    f"✅ {ism} tasdiqlandi. Shaxsiy mavzu *{ism} — {role_txt} | {filial}* ochildi.",
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
            except Exception:
                pass

        elif action == "block":
            await db.block_xodim(target_uid)
            await query.edit_message_text("🚫 Xodim bloklandi.")
            try:
                await context.bot.send_message(
                    chat_id=target_uid,
                    text="🚫 Profilingiz ma'muriyat tomonidan bloklandi.",
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
            except Exception:
                pass
        return

    # ── Xodimlar sahifalash ───────────────────────────────────────
    if data.startswith("xod_page_"):
        page = int(data.split("_")[2])
        rows = await db.get_approved_xodimlar()
        if not rows:
            await query.edit_message_text("👥 Tizimda faol xodimlar hozircha yo'q.")
            return
        total = len(rows)
        start = page * PAGE_SIZE
        end   = min(start + PAGE_SIZE, total)
        matn  = f"👥 *Faol xodimlar ({start + 1}–{end} / {total}):*\n\n"
        for r in rows[start:end]:
            matn += f"👤 *{r[0]}* | {r[1]} | Kod: `{r[3]}` | ID: `{r[4]}`\n"
        await query.edit_message_text(
            matn,
            parse_mode="Markdown",
            reply_markup=xodimlar_page_inline(page, total),
        )
        return

    # ── Vazifa holati ─────────────────────────────────────────────
    if data.startswith(("prog_", "done_")):
        action, task_id = data.split("_", 1)[0], int(data.split("_", 1)[1])
        task = await db.get_xabar(task_id)
        if not task:
            await query.edit_message_text("❌ Topshiriq topilmadi.")
            return
        t_uid, x_ism, msg_id, holat = task

        if action == "prog":
            if holat == "bajarildi":
                await query.answer("Bu topshiriq allaqachon bajarilgan!", show_alert=True)
                return
            await db.update_xabar_holat(task_id, "jarayonda")
            await query.edit_message_text(
                f"🔄 #{task_id} jarayonga olindi.",
                reply_markup=bajarildi_inline(task_id),
            )
            try:
                await context.bot.send_message(
                    chat_id=t_uid,
                    text=f"🔄 #{task_id}-sonli so'rovingiz ko'rib chiqish jarayoniga o'tkazildi.",
                    reply_to_message_id=msg_id,
                )
            except Exception:
                pass

        elif action == "done":
            await db.update_xabar_holat(task_id, "bajarildi")
            await query.edit_message_text(f"✅ #{task_id}-sonli vazifa yakunlandi!")
            try:
                await context.bot.send_message(
                    chat_id=t_uid,
                    text=f"✅ #{task_id}-sonli so'rov muvaffaqiyatli bajarildi.",
                    reply_to_message_id=msg_id,
                )
            except Exception:
                pass


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
    except Exception:
        pass
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
    query = update.message.text.strip()
    rows  = await db.search_xodimlar(query)

    if not rows:
        await update.message.reply_text(
            f"❌ *'{query}'* bo'yicha hech qanday xodim topilmadi.",
            parse_mode="Markdown",
            reply_markup=admin_kb(),
        )
        return ConversationHandler.END

    matn = f"🔍 *'{query}' bo'yicha natijalar ({len(rows)} ta):*\n\n"
    for r in rows:
        matn += f"👤 *{r[0]}* | {r[1]} | 🏢 {r[2]} | Kod: `{r[3]}` | ID: `{r[4]}`\n"

    await update.message.reply_text(matn, parse_mode="Markdown", reply_markup=admin_kb())
    return ConversationHandler.END
