"""
handlers/admin_cmd.py — Admin buyruqlari va xodim boshqaruvi.
"""
import logging
import os
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import (
    admin_kb, edit_field_kb, remove_kb,
    xodimlar_edit_page_inline, xodim_profil_kb,
    search_results_kb,
    pending_xodimlar_inline, blocked_xodimlar_inline,
)
from config import (
    ADMIN_ID, PAGE_SIZE,
    EDIT_FIELD, EDIT_VALUE, SEARCH_QUERY,
    ADD_ADMIN_ID,
)
from handlers._shared import em, admin_only, _format_profil

logger = logging.getLogger(__name__)


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
    from config import ADMIN_ID as _MAIN
    from keyboards import admins_mgmt_kb
    admins = await db.get_admins()
    lines = ["👑 *Admin boshqaruvi*\n"]
    for aid in admins:
        row = await db.get_xodim(aid)
        ism = row[2] if row else str(aid)
        badge = " *(Asosiy)*" if aid == _MAIN else ""
        lines.append(f"• {em(ism)} — `{aid}`{badge}")
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=admins_mgmt_kb(admins, _MAIN),
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
        f"✅ `{new_id}` admin sifatida qo'shildi\\. U `/start` bosishi kerak\\.",
        parse_mode="MarkdownV2",
        reply_markup=admin_kb(),
    )
    try:
        await context.bot.send_message(
            chat_id=new_id,
            text="🎉 Siz admin sifatida qo'shildingiz\\! /start bosing\\.",
            parse_mode="MarkdownV2",
        )
    except Exception:
        pass
    return ConversationHandler.END


async def admin_mgmt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID as _MAIN
    from keyboards import admins_mgmt_kb
    query = update.callback_query
    await query.answer()
    if not await db.is_admin(query.from_user.id):
        return ConversationHandler.END

    if query.data == "admin_noop":
        return ADD_ADMIN_ID

    if query.data == "admin_add":
        await query.edit_message_text(
            "➕ *Yangi admin qo'shish*\n\nYangi adminning *User ID* sini yuboring:\n\n"
            "💡 @userinfobot ga /start yuboring — User ID topasiz.",
            parse_mode="Markdown",
        )
        return ADD_ADMIN_ID

    if query.data.startswith("admin_rm_"):
        try:
            target_id = int(query.data[len("admin_rm_"):])
        except ValueError:
            await query.answer("❌ Noto'g'ri ID.", show_alert=True)
            return ADD_ADMIN_ID
        if target_id == _MAIN:
            await query.answer("Asosiy adminni chiqarib bo'lmaydi!", show_alert=True)
            return ADD_ADMIN_ID
        await db.remove_admin(target_id)
        admins = await db.get_admins()
        lines = ["👑 *Admin boshqaruvi*\n"]
        for aid in admins:
            row = await db.get_xodim(aid)
            ism = row[2] if row else str(aid)
            badge = " *(Asosiy)*" if aid == _MAIN else ""
            lines.append(f"• {em(ism)} — `{aid}`{badge}")
        try:
            await query.edit_message_text(
                "\n".join(lines),
                parse_mode="Markdown",
                reply_markup=admins_mgmt_kb(admins, _MAIN),
            )
        except Exception:
            pass
        await query.answer(f"✅ {target_id} adminlikdan chiqarildi.", show_alert=True)
        return ADD_ADMIN_ID

    return ADD_ADMIN_ID


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


_DATE_LABEL = {
    "all":        "",
    "today":      " | Bugun",
    "yesterday":  " | Kecha",
    "this_month": " | Shu oy",
    "last_month": " | O'tgan oy",
}


async def _send_tarix(send_fn, logs: list,
                      filter_type: str = "all", date_filter: str = "all"):
    from keyboards import tarix_filter_kb
    date_lbl = _DATE_LABEL.get(date_filter, "")
    if not logs:
        text = f"📋 *O'zgarishlar tarixi bo'sh.*{date_lbl}"
    else:
        text = f"📋 *O'zgarishlar tarixi*{date_lbl}\n\n"
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
                if hasattr(created_at, "strftime"):
                    time_str = created_at.strftime("%d.%m.%Y %H:%M")
                else:
                    dt       = datetime.strptime(str(created_at)[:19], "%Y-%m-%d %H:%M:%S")
                    time_str = dt.strftime("%d.%m.%Y %H:%M")
            except Exception:
                time_str = str(created_at or "")[:16]
            text += (
                f"{i}. 👤 *{em(user_name)}* ({role_lbl})\n"
                f"   {icon} {label}{target_part}\n"
                f"   🕐 {time_str}\n"
                f"   {s_icon} {s_label}\n\n"
            )
    await send_fn(text, parse_mode="Markdown",
                  reply_markup=tarix_filter_kb(filter_type, date_filter))


@admin_only
async def admin_tarix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    filter_type = context.user_data.get("tarix_filter", "all")
    date_filter = context.user_data.get("tarix_date",   "all")
    logs = await db.get_audit_logs(filter_type=filter_type, date_filter=date_filter)
    await _send_tarix(update.message.reply_text, logs, filter_type, date_filter)


async def tarix_filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await db.is_admin(query.from_user.id):
        return

    data = query.data  # tarix_f_<role> yoki tarix_d_<date>
    if data.startswith("tarix_f_"):
        context.user_data["tarix_filter"] = data[len("tarix_f_"):]
    elif data.startswith("tarix_d_"):
        # ikkinchi marta bosish → filter o'chirilsin (all ga qaytsin)
        new_date = data[len("tarix_d_"):]
        if context.user_data.get("tarix_date") == new_date:
            new_date = "all"
        context.user_data["tarix_date"] = new_date

    filter_type = context.user_data.get("tarix_filter", "all")
    date_filter = context.user_data.get("tarix_date",   "all")
    logs = await db.get_audit_logs(filter_type=filter_type, date_filter=date_filter)
    await _send_tarix(query.edit_message_text, logs, filter_type, date_filter)
