import logging

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from config import (
    TOKEN,
    ISM, LAVOZIM, KOD, FILIAL, TELEFON, TELEFON2, TUGILGAN_KUN,
    EDIT_USER, EDIT_FIELD, EDIT_VALUE,
)
from database import init_db
from handlers import (
    start,
    ism_olish, lavozim_olish, kod_olish,
    filial_olish, telefon_olish, telefon2_olish,
    tugilgan_kun_olish,
    xodim_chat_handler,
    admin_guruh_javob,
    callback_handler,
    admin_statistika, admin_xodimlar,
    admin_kutilayotganlar, admin_bloklanganlar,
    admin_excel_eksport,
    start_edit, edit_user_id, edit_field, edit_value,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def build_application() -> Application:
    app = Application.builder().token(TOKEN).build()

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
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    # ── Xodimni tahrirlash ConversationHandler ───────────────────
    tahrir_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📝 Xodimni Tahrirlash$"), start_edit)],
        states={
            EDIT_USER:  [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_user_id)],
            EDIT_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field)],
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    app.add_handler(royxat_conv)
    app.add_handler(tahrir_conv)

    app.add_handler(MessageHandler(filters.Regex(r"^📊 Statistika$"),             admin_statistika))
    app.add_handler(MessageHandler(filters.Regex(r"^👥 Xodimlar$"),               admin_xodimlar))
    app.add_handler(MessageHandler(filters.Regex(r"^⏳ Kutilayotgan so'rovlar$"), admin_kutilayotganlar))
    app.add_handler(MessageHandler(filters.Regex(r"^🚫 Bloklanganlar$"),          admin_bloklanganlar))
    app.add_handler(MessageHandler(filters.Regex(r"^📥 Excel Eksport$"),          admin_excel_eksport))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, admin_guruh_javob))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, xodim_chat_handler))

    return app


async def post_init(app: Application):
    await init_db()
    logger.info("✅ Ma'lumotlar bazasi tayyor.")


async def error_handler(update: object, context) -> None:
    logger.error("Kutilmagan xato:", exc_info=context.error)


def main():
    logger.info("🚀 Dusel Company boti ishga tushmoqda...")
    app = build_application()
    app.post_init = post_init
    app.add_error_handler(error_handler)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
