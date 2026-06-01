import logging
from telegram import Update
from telegram.ext import ContextTypes

import database as db
from keyboards import faq_kategoriyalar_kb, faq_savollar_kb, faq_javob_kb

logger = logging.getLogger(__name__)


async def faq_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await db.get_faq_kategoriyalar()
    if not rows:
        await update.message.reply_text("📭 Hozircha savollar mavjud emas.")
        return
    await update.message.reply_text(
        "❔ *Ko'p so'raladigan savollar*\n\nKategoriyani tanlang:",
        parse_mode="Markdown",
        reply_markup=faq_kategoriyalar_kb(rows),
    )


async def faq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "faq_back":
        rows = await db.get_faq_kategoriyalar()
        if not rows:
            await query.edit_message_text("📭 Hozircha savollar mavjud emas.")
            return
        await query.edit_message_text(
            "❔ *Ko'p so'raladigan savollar*\n\nKategoriyani tanlang:",
            parse_mode="Markdown",
            reply_markup=faq_kategoriyalar_kb(rows),
        )

    elif data.startswith("faq_kat_"):
        kat_id = int(data.split("_")[-1])
        rows = await db.get_faq_savollar(kat_id)
        if not rows:
            all_cats = await db.get_faq_kategoriyalar()
            await query.edit_message_text(
                "📭 Bu kategoriyada hali savollar yo'q.\n\nBoshqa kategoriyani tanlang:",
                reply_markup=faq_kategoriyalar_kb(all_cats),
            )
            return
        await query.edit_message_text(
            "❔ Savolni tanlang:",
            reply_markup=faq_savollar_kb(rows, kat_id),
        )

    elif data.startswith("faq_sav_"):
        faq_id = int(data.split("_")[-1])
        item = await db.get_faq_item(faq_id)
        if not item:
            await query.edit_message_text("❌ Savol topilmadi.")
            return
        savol, javob, kat_id = item
        await query.edit_message_text(
            f"❔ *{savol}*\n\n{javob}",
            parse_mode="Markdown",
            reply_markup=faq_javob_kb(faq_id, kat_id),
        )
