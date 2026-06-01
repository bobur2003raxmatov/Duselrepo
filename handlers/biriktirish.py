"""
handlers/biriktirish.py — Biriktirish handlerlari (Agent↔Checker).
"""
import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import (
    biriktirish_list_kb, biriktir_detail_kb,
    biriktirish_agents_kb, biriktirish_checkers_kb,
)
from config import (
    BIRIKTIR_AGENT, BIRIKTIR_CHECKER, BIRIKTIR_DETAIL,
    BIRIKTIR_EDIT_VALUE,
)
from handlers._shared import em, admin_only, _format_profil

logger = logging.getLogger(__name__)


def _format_profil_local(row: tuple) -> str:
    """Local alias — _format_profil ni qayta ishlatish."""
    return _format_profil(row)


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
