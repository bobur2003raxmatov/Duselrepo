import logging
import datetime
import warnings

from telegram import BotCommand

from telegram.warnings import PTBUserWarning
warnings.filterwarnings("ignore", message=".*per_message=False.*", category=PTBUserWarning)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from config import (
    TOKEN, GROUP_CHAT_ID,
    ISM, LAVOZIM, KOD, FILIAL, TELEFON, TELEFON2, TUGILGAN_KUN,
    EDIT_USER, EDIT_FIELD, EDIT_VALUE, SEARCH_QUERY,
)
from database import init_db
from utils import daily_report_job
from handlers import (
    start, cancel,
    ism_olish, lavozim_olish, kod_olish,
    filial_olish, telefon_olish, telefon2_olish,
    tugilgan_kun_olish,
    xodim_chat_handler,
    admin_guruh_javob,
    callback_handler,
    admin_statistika, admin_xodimlar,
    admin_kutilayotganlar, admin_bloklanganlar,
    admin_excel_eksport,
    admin_search, search_query_handler,
    start_edit, edit_page, edit_select_user, edit_search, edit_field, edit_value,
)

# ── Logging: console + file ───────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def build_application() -> Application:
    app = Application.builder().token(TOKEN).build()

    cancel_cmd = CommandHandler("cancel", cancel)

    # ── Ro'yxatdan o'tish ConversationHandler ────────────────────
    royxat_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ISM:          [MessageHandler(filters.TEXT & ~filters.COMMAND, ism_olish)],
            LAVOZIM:      [MessageHandler(filters.TEXT & ~filters.COMMAND, lavozim_olish)],
            KOD:          [MessageHandler(filters.TEXT & ~filters.COMMAND, kod_olish)],
            FILIAL:       [MessageHandler(filters.TEXT & ~filters.COMMAND, filial_olish)],
            TELEFON:      [MessageHandler(filters.CONTACT, telefon_olish)],
            TELEFON2:     [
                MessageHandler(filters.CONTACT, telefon2_olish),
                MessageHandler(filters.TEXT & ~filters.COMMAND, telefon2_olish),
            ],
            TUGILGAN_KUN: [MessageHandler(filters.TEXT & ~filters.COMMAND, tugilgan_kun_olish)],
        },
        fallbacks=[cancel_cmd, CommandHandler("start", start)],
        allow_reentry=True,
    )

    # ── Xodimni tahrirlash ConversationHandler ───────────────────
    tahrir_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📝 Xodimni Tahrirlash$"), start_edit)],
        states={
            EDIT_USER: [
                CallbackQueryHandler(edit_select_user, pattern="^edit_select_"),
                CallbackQueryHandler(edit_page,        pattern="^edit_page_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_search),
            ],
            EDIT_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field)],
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value)],
        },
        fallbacks=[cancel_cmd, CommandHandler("start", start)],
        allow_reentry=True,
        per_message=False,
    )

    # ── Xodim qidirish ConversationHandler ──────────────────────
    qidiruv_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^🔍 Xodim Qidirish$"), admin_search)],
        states={
            SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_query_handler)],
        },
        fallbacks=[cancel_cmd, CommandHandler("start", start)],
        allow_reentry=True,
    )

    app.add_handler(royxat_conv)
    app.add_handler(tahrir_conv)
    app.add_handler(qidiruv_conv)
    app.add_handler(cancel_cmd)

    app.add_handler(MessageHandler(filters.Regex(r"^📊 Statistika$"),             admin_statistika))
    app.add_handler(MessageHandler(filters.Regex(r"^👥 Xodimlar$"),               admin_xodimlar))
    app.add_handler(MessageHandler(filters.Regex(r"^⏳ Kutilayotgan so'rovlar$"), admin_kutilayotganlar))
    app.add_handler(MessageHandler(filters.Regex(r"^🚫 Bloklanganlar$"),          admin_bloklanganlar))
    app.add_handler(MessageHandler(filters.Regex(r"^📥 Excel Eksport$"),          admin_excel_eksport))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Chat(GROUP_CHAT_ID) & ~filters.COMMAND, admin_guruh_javob))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, xodim_chat_handler))

    return app


async def post_init(app: Application):
    await init_db()
    logger.info("✅ Ma'lumotlar bazasi tayyor.")
    await app.bot.set_my_commands([
        BotCommand("start",  "Botni qayta ishga tushirish"),
        BotCommand("cancel", "Jarayonni bekor qilish"),
    ])
    # General topicda faqat adminlar yoza olsin
    try:
        from telegram import ChatPermissions
        await app.bot.set_chat_permissions(
            chat_id=GROUP_CHAT_ID,
            permissions=ChatPermissions(can_send_messages=False),
        )
        logger.info("✅ General topic: faqat adminlar yoza oladi.")
    except Exception as e:
        logger.warning(f"General topic cheklovini o'rnatishda xato: {e}")

    # Daily report at 09:00 Tashkent time (UTC+5)
    tz_uz = datetime.timezone(datetime.timedelta(hours=5))
    app.job_queue.run_daily(
        daily_report_job,
        time=datetime.time(hour=9, minute=0, tzinfo=tz_uz),
    )
    logger.info("✅ Kunlik hisobot rejalashtirildi: 09:00 (UTC+5)")


async def error_handler(update: object, context) -> None:
    from telegram.error import NetworkError, TimedOut
    if isinstance(context.error, (NetworkError, TimedOut)):
        logger.warning(f"Tarmoq xatosi (vaqtinchalik): {context.error}")
        return
    logger.error("Kutilmagan xato:", exc_info=context.error)


def main():
    logger.info("🚀 Dusel Company boti ishga tushmoqda...")
    app = build_application()
    app.post_init = post_init
    app.add_error_handler(error_handler)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
