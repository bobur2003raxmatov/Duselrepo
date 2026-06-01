"""
handlers/chat.py — Xodim↔Admin xabar yo'naltirish, reaksiyalar, topic yopilish.
"""
import logging

from telegram import Update, ReplyParameters
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from config import GROUP_CHAT_ID, ADMIN_ID
from keyboards import remove_kb, tasdiq_inline
from handlers._shared import em, rate_limited, _msg_ctype, _role_keyboard

logger = logging.getLogger(__name__)


async def xodim_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.chat.id == GROUP_CHAT_ID:
        return

    uid = update.effective_user.id
    if await db.is_admin(uid):
        return

    # Conversation oqimida bo'lsa o'tkazib yuborish
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
    if rate_limited(uid):
        return

    # Tasdiqlangan lekin topic_id yo'q → avtomatik yaratish
    if not topic_id:
        try:
            role_txt = f"{lavozim} ({kod})" if kod and kod != "KOD YO'Q" else lavozim
            topic = await context.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID,
                name=f"{ism} — {role_txt} | {filial}",
            )
            topic_id = topic.message_thread_id
            await db.approve_xodim(uid, topic_id)
        except Exception as e:
            logger.warning(f"Topic avtomatik yaratishda xato (uid={uid}): {e}")
            await msg.reply_text("❌ Shaxsiy mavzungiz yo'q. Admin bilan bog'laning.")
            return

    # Agar xodim admin javobiga reply qilayotgan bo'lsa — topicda ham reply qilish
    reply_to_group_msg_id = None
    if msg.reply_to_message:
        reply_to_group_msg_id = await db.get_group_msg_id_by_private(
            uid, msg.reply_to_message.message_id
        )

    thread_kwargs = {"message_thread_id": topic_id}

    try:
        sent = await context.bot.copy_message(
            chat_id=GROUP_CHAT_ID,
            from_chat_id=msg.chat_id,
            message_id=msg.message_id,
            reply_to_message_id=reply_to_group_msg_id,
            allow_sending_without_reply=True,
            **thread_kwargs,
        )
        xabar_id = await db.insert_xabar(uid, ism, filial, _msg_ctype(msg), msg.message_id)
        await db.update_xabar_group_fwd_id(xabar_id, sent.message_id)

    except BadRequest as e:
        err = str(e).lower()
        if "message thread not found" in err or "topic" in err or "thread" in err:
            await db.reset_topic(uid)
            await msg.reply_text(
                "⚠️ Guruhdagi mavzungiz o'chirilgan. Admin qayta tasdiqlashini kuting.",
                reply_markup=_role_keyboard(lavozim),
            )
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🔄 *Mavzusi o'chirilgan xodim:*\n\n👤 {em(ism)} | {em(lavozim)}",
                    parse_mode="Markdown",
                    reply_markup=tasdiq_inline(uid),
                )
            except Exception:
                pass
        else:
            logger.warning(f"Xabarni topicga yuborishda xato (uid={uid}): {e}")
    except Exception as e:
        logger.warning(f"Xabarni topicga yuborishda xato (uid={uid}): {e}")


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
    if cid == GROUP_CHAT_ID and await db.is_admin(uid):
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


async def admin_guruh_javob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.message_thread_id:
        return
    if msg.chat.id != GROUP_CHAT_ID or not await db.is_admin(update.effective_user.id):
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


async def matn_javob_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """matn_javob buyruqli tugma bosilganda admin belgilagan matnni qaytaradi."""
    from handlers.menu_dispatch import get_matn_extra
    text = update.message.text or ""
    javob = get_matn_extra(text)
    if javob:
        await update.message.reply_text(javob)
