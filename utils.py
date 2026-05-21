import os
import logging
import tempfile
import pandas as pd
from datetime import datetime

from telegram.ext import ContextTypes
from config import GROUP_CHAT_ID, ADMIN_ID

logger = logging.getLogger(__name__)


async def is_topic_valid(context: ContextTypes.DEFAULT_TYPE, topic_id: int | None) -> bool:
    if not topic_id:
        return False
    try:
        test = await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            message_thread_id=topic_id,
            text=".",
            disable_notification=True,
        )
        await context.bot.delete_message(chat_id=GROUP_CHAT_ID, message_id=test.message_id)
        return True
    except Exception:
        return False


async def check_sla_timeout(context: ContextTypes.DEFAULT_TYPE):
    from database import get_xabar
    job      = context.job
    task_id  = job.data["task_id"]
    topic_id = job.data["topic_id"]
    x_ism    = job.data["x_ism"]
    reminder = job.data.get("reminder", 1)

    row = await get_xabar(task_id)
    if not row or row[3] != "kutilmoqda":
        return

    minutes = 15 * reminder
    ogohlantirish = (
        f"🚨 *DIQQAT! #SLA Nazorati ({reminder}-eslatma)*\n\n"
        f"⚠️ #{task_id}-sonli topshiriq kelganiga *{minutes} daqiqa* bo'ldi, "
        f"biroq haligacha belgilanmadi!\n"
        f"👤 Xodim: {x_ism}"
    )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID, text=ogohlantirish, parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Admin SLA xabari yuborishda xato: {e}")

    if topic_id:
        try:
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic_id,
                text=ogohlantirish,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Topic SLA xabari yuborishda xato: {e}")


async def daily_report_job(context: ContextTypes.DEFAULT_TYPE):
    from database import get_statistika, get_kunlik_statistika
    stat   = await get_statistika()
    kunlik = await get_kunlik_statistika()
    today  = datetime.now().strftime("%d.%m.%Y")

    matn = (
        f"📅 *{today} — Kunlik Hisobot*\n\n"
        f"📥 Jami xabarlar: *{stat['jami']}*\n"
        f"✅ Bajarilgan: *{stat['bajarilgan']}*\n"
        f"⏳ Kutilmoqda: *{stat['kutilmoqda']}*\n"
        f"⏱ O'rtacha vaqt: *{stat['ortacha']} daqiqa*"
    )
    if kunlik:
        matn += "\n\n*📊 Bugungi faollik:*\n"
        for row in kunlik:
            matn += f"• {row[0]} ({row[1]}): {row[2]} ta, {row[3]} bajarildi\n"
    else:
        matn += "\n\n_Bugun hech qanday faollik yo'q._"

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID, text=matn, parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Kunlik hisobot yuborishda xato: {e}")


async def generate_excel(x_data: list, m_data: list) -> str:
    suffix = f"_Dusel_Hisobot_{datetime.now().strftime('%d_%m_%Y')}.xlsx"
    fd, filename = tempfile.mkstemp(suffix=suffix)
    os.close(fd)

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        pd.DataFrame(
            x_data,
            columns=[
                "User ID", "Ism", "Lavozim", "Kod", "Filial",
                "Tel 1", "Tel 2", "Tug'ilgan kun", "Status", "Ro'yxatdan o'tgan sana",
            ]
        ).to_excel(writer, sheet_name="Xodimlar", index=False)

        pd.DataFrame(
            m_data,
            columns=[
                "Vazifa ID", "Xodim ID", "Xodim Ismi", "Filial",
                "Xabar Turi", "Xabar Kelgan Vaqt", "Xabar Holati", "Bajarilgan Vaqt",
            ]
        ).to_excel(writer, sheet_name="Topshiriqlar_SLA", index=False)

    return filename
