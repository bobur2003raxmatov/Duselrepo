"""
handlers/callbacks.py — Callback handler dispatcher va yordamchi funksiyalar.
"""
import logging
import os

from telegram import Update, ReplyParameters
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import (
    xodimlar_page_inline, xodim_profil_kb,
    group_sorov_inline, group_bajarildi_inline, group_detail_back_inline,
    bajarildi_inline, checker_sorov_kb,
    pending_xodimlar_inline, blocked_xodimlar_inline,
    klientlar_search_page_inline,
)
from config import (
    ADMIN_ID, GROUP_CHAT_ID, PAGE_SIZE,
    URGENCY_TIMEOUT_SEC, CHECKER_TIMEOUT_SEC,
)
from handlers._shared import em, safe_callback_int, _format_profil, _schedule_sla
from handlers.admin_cmd import _send_pending_page, _send_blocked_page
from handlers.klient import klient_view_callback, klient_approve_callback, klient_reject_callback

logger = logging.getLogger(__name__)


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
            from handlers._shared import _role_keyboard
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
        if holat == "bajarildi":
            await query.answer("Bu guruh allaqachon bajarilgan!", show_alert=True)
            return

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

    if not await db.is_admin(query.from_user.id):
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
        from utils import generate_excel
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
        from utils import generate_klientlar_excel
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
        from utils import generate_full_excel
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
