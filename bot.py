import logging
import datetime
import warnings

from telegram import BotCommand, ChatPermissions, Update

from telegram.warnings import PTBUserWarning
warnings.filterwarnings("ignore", message=".*per_message=False.*", category=PTBUserWarning)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageReactionHandler,
    filters,
)

from config import (
    TOKEN, GROUP_CHAT_ID,
    ISM, LAVOZIM, KOD, FILIAL, TELEFON, TELEFON2, TUGILGAN_KUN,
    EDIT_USER, EDIT_FIELD, EDIT_VALUE, SEARCH_QUERY,
    BIRIKTIR_AGENT, BIRIKTIR_CHECKER, BIRIKTIR_DETAIL,
    BIRIKTIR_EDIT_FIELD, BIRIKTIR_EDIT_VALUE,
    KLIENT_RASM, KLIENT_FIRMA_NOMI, KLIENT_TELEFON1, KLIENT_TELEFON2,
    KLIENT_INN, KLIENT_ORIENTER, KLIENT_LOKATSIYA, KLIENT_KATEGORIYA,
    KLIENT_DOKON_TURI, KLIENT_DISTRIBUTOR, KLIENT_AGENT_KOD,
    KLIENT_VIZIT_KUN, KLIENT_CHASTOTA, KLIENT_LIMIT, KLIENT_BRENDLAR,
    KLIENT_CONFIRM,
)
from database import init_db
from utils import daily_report_job, weekly_report_job, agent_reminder_job
from handlers import (
    reaction_handler,
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
    admin_biriktirish,
    biriktir_list_cb, biriktir_new_cb, biriktir_agent_cb, biriktir_back_cb,
    biriktir_change_cb, biriktir_rm_cb, biriktir_block_cb,
    biriktir_edit_field_cb, biriktir_edit_value_handler,
    biriktir_checker_cb,
    admin_agent_reyting, admin_filial_lider,
    start_edit, edit_page, edit_select_user, edit_search, edit_field, edit_value,
    start_klient_registration, klient_rasm, klient_firma_nomi, klient_telefon1,
    klient_telefon2, klient_inn, klient_orienter, klient_lokatsiya, klient_kategoriya,
    klient_dokon_turi, klient_distributor, klient_agent_kod, klient_vizit_kun,
    klient_chastota, klient_limit, klient_brendlar, klient_confirm,
    admin_klientlar, klient_view_callback, klient_approve_callback, klient_reject_callback,
    klient_reject_reason,
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

    # ── Biriktirish ConversationHandler (to'liq agent boshqaruv) ─
    biriktir_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^🔗 Biriktirish$"), admin_biriktirish)],
        states={
            BIRIKTIR_AGENT: [
                CallbackQueryHandler(biriktir_list_cb,  pattern="^bir_detail_"),
                CallbackQueryHandler(biriktir_new_cb,   pattern="^bir_new$"),
                CallbackQueryHandler(biriktir_agent_cb, pattern="^bir_agent_"),
                CallbackQueryHandler(biriktir_back_cb,  pattern="^bir_back$"),
            ],
            BIRIKTIR_DETAIL: [
                CallbackQueryHandler(biriktir_change_cb,      pattern="^bir_change_"),
                CallbackQueryHandler(biriktir_rm_cb,          pattern="^bir_rm_"),
                CallbackQueryHandler(biriktir_block_cb,       pattern="^bir_block_|^bir_unblock_"),
                CallbackQueryHandler(biriktir_edit_field_cb,  pattern="^bir_ef_"),
                CallbackQueryHandler(biriktir_back_cb,        pattern="^bir_back$"),
            ],
            BIRIKTIR_CHECKER: [
                CallbackQueryHandler(biriktir_checker_cb, pattern="^bir_checker_|^bir_none$|^bir_back$"),
            ],
            BIRIKTIR_EDIT_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, biriktir_edit_value_handler),
            ],
        },
        fallbacks=[cancel_cmd, CommandHandler("start", start)],
        allow_reentry=True,
        per_message=False,
    )

    # ── Klient registratsiya ConversationHandler (16 qadam) ──────
    klient_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^🏪 Yangi Klient$"), start_klient_registration)],
        states={
            KLIENT_RASM:        [MessageHandler(filters.PHOTO, klient_rasm)],
            KLIENT_FIRMA_NOMI:  [MessageHandler(filters.TEXT & ~filters.COMMAND, klient_firma_nomi)],
            KLIENT_TELEFON1:    [MessageHandler(filters.CONTACT, klient_telefon1)],
            KLIENT_TELEFON2:    [MessageHandler(filters.CONTACT | filters.Regex(r"^⏭"), klient_telefon2)],
            KLIENT_INN:         [MessageHandler(filters.TEXT & ~filters.COMMAND, klient_inn)],
            KLIENT_ORIENTER:    [MessageHandler(filters.TEXT & ~filters.COMMAND, klient_orienter)],
            KLIENT_LOKATSIYA:   [MessageHandler(filters.LOCATION, klient_lokatsiya)],
            KLIENT_KATEGORIYA:  [CallbackQueryHandler(klient_kategoriya, pattern="^klient_kat_")],
            KLIENT_DOKON_TURI:  [CallbackQueryHandler(klient_dokon_turi, pattern="^klient_tur_")],
            KLIENT_DISTRIBUTOR: [CallbackQueryHandler(klient_distributor, pattern="^klient_dist_")],
            KLIENT_AGENT_KOD:   [CallbackQueryHandler(klient_agent_kod, pattern="^klient_agent_")],
            KLIENT_VIZIT_KUN:   [CallbackQueryHandler(klient_vizit_kun, pattern="^klient_kun_")],
            KLIENT_CHASTOTA:    [CallbackQueryHandler(klient_chastota, pattern="^klient_chas_")],
            KLIENT_LIMIT:       [MessageHandler(filters.TEXT & ~filters.COMMAND, klient_limit)],
            KLIENT_BRENDLAR:    [CallbackQueryHandler(klient_brendlar, pattern="^klient_brand_|^klient_brands_confirm|^klient_cancel$")],
            KLIENT_CONFIRM:     [CallbackQueryHandler(klient_confirm, pattern="^klient_submit|^klient_cancel$")],
        },
        fallbacks=[cancel_cmd, CommandHandler("start", start)],
        allow_reentry=True,
        per_message=False,
    )

    app.add_handler(royxat_conv)
    app.add_handler(tahrir_conv)
    app.add_handler(qidiruv_conv)
    app.add_handler(biriktir_conv)
    app.add_handler(klient_conv)
    app.add_handler(cancel_cmd)

    app.add_handler(MessageHandler(filters.Regex(r"^⭐ Agent Reytingi$"),          admin_agent_reyting))
    app.add_handler(MessageHandler(filters.Regex(r"^🏆 Filial Reytingi$"),         admin_filial_lider))
    app.add_handler(MessageHandler(filters.Regex(r"^📊 Statistika$"),             admin_statistika))
    app.add_handler(MessageHandler(filters.Regex(r"^👥 Xodimlar$"),               admin_xodimlar))
    app.add_handler(MessageHandler(filters.Regex(r"^⏳ Kutilayotgan so'rovlar$"), admin_kutilayotganlar))
    app.add_handler(MessageHandler(filters.Regex(r"^🚫 Bloklanganlar$"),          admin_bloklanganlar))
    app.add_handler(MessageHandler(filters.Regex(r"^📥 Excel$"),                  admin_excel_eksport))
    app.add_handler(MessageHandler(filters.Regex(r"^🏪 Klientlar$"),              admin_klientlar))
    app.add_handler(MessageReactionHandler(reaction_handler))

    # Klient reject reason handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, klient_reject_reason))

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
        await app.bot.set_chat_permissions(
            chat_id=GROUP_CHAT_ID,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_other_messages=False,  # sticker/GIF ham yo'q (faqat admin)
            ),
        )
        logger.info("✅ General topic: faqat adminlar yoza oladi.")
    except Exception as e:
        logger.warning(f"General topic cheklovini o'rnatishda xato: {e}")


    tz_uz = datetime.timezone(datetime.timedelta(hours=5))

    # Daily report at 09:00
    app.job_queue.run_daily(
        daily_report_job,
        time=datetime.time(hour=9, minute=0, tzinfo=tz_uz),
    )
    logger.info("✅ Kunlik hisobot rejalashtirildi: 09:00 (UTC+5)")

    # Weekly report every Monday at 09:00 (feature 15)
    app.job_queue.run_daily(
        weekly_report_job,
        time=datetime.time(hour=9, minute=0, tzinfo=tz_uz),
        days=(0,),  # 0 = Monday
    )
    logger.info("✅ Haftalik hisobot rejalashtirildi: Dushanba 09:00 (UTC+5)")

    # Agent reminder every day at 17:00 (feature 18)
    app.job_queue.run_daily(
        agent_reminder_job,
        time=datetime.time(hour=17, minute=0, tzinfo=tz_uz),
    )
    logger.info("✅ Agent eslatmasi rejalashtirildi: 17:00 (UTC+5)")


async def error_handler(update: object, context) -> None:
    from telegram.error import NetworkError, TimedOut, Conflict
    if isinstance(context.error, (NetworkError, TimedOut, Conflict)):
        logger.warning(f"Tarmoq xatosi (vaqtinchalik): {context.error}")
        return
    logger.error("Kutilmagan xato:", exc_info=context.error)


def main():
    logger.info("🚀 Dusel Company boti ishga tushmoqda...")
    app = build_application()
    app.post_init = post_init
    app.add_error_handler(error_handler)
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
