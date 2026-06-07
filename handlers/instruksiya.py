"""
handlers/instruksiya.py — Instruksiya handlerlari.
"""
import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import admin_kb, instruksiya_lavozim_kb, instruksiya_mavjud_kb
from config import INSTR_MATN
from handlers._shared import admin_only

logger = logging.getLogger(__name__)


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
    await db.delete_instruksiya(lavozim)
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
