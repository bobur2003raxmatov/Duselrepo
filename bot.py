import os
import sys

# ── Django setup (modellar import bo'lishidan oldin) ──────────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dusel.settings")
import django
django.setup()
# ──────────────────────────────────────────────────────────────────

# ── Startup diagnostics (runs before any import that can fail) ─────
print("=== BOT STARTUP ===", flush=True)
print(f"TOKEN      : {'SET' if os.environ.get('TOKEN') else '*** NOT SET ***'}", flush=True)
print(f"WEBHOOK_URL: {os.environ.get('WEBHOOK_URL') or '*** NOT SET ***'}", flush=True)
print(f"PORT       : {os.environ.get('PORT', '8443')}", flush=True)
print(f"ADMIN_ID   : {os.environ.get('ADMIN_ID', 'NOT SET')}", flush=True)
print("===================", flush=True)

if not os.environ.get("TOKEN"):
    print("FATAL: TOKEN environment variable is not set. Exiting.", flush=True)
    sys.exit(1)
# ───────────────────────────────────────────────────────────────────

print("=== STARTING IMPORTS ===", flush=True)

import traceback
import logging
import datetime
import warnings
import fcntl
print("stdlib imported OK", flush=True)

from telegram import BotCommand, ChatPermissions, Update
from telegram.ext import PicklePersistence
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
print("telegram imported OK", flush=True)

from config import (
    TOKEN, GROUP_CHAT_ID, WEBHOOK_URL, PORT,
    ISM, LAVOZIM, KOD, FILIAL, TELEFON, TELEFON2, TUGILGAN_KUN,
    XODIM_LIST, EDIT_FIELD, EDIT_VALUE, SEARCH_QUERY,
    BIRIKTIR_AGENT, BIRIKTIR_CHECKER, BIRIKTIR_DETAIL,
    BIRIKTIR_EDIT_VALUE,
    KLIENT_RASM, KLIENT_FIRMA_NOMI, KLIENT_TELEFON1, KLIENT_TELEFON2,
    KLIENT_INN, KLIENT_ORIENTER, KLIENT_LOKATSIYA, KLIENT_KATEGORIYA,
    KLIENT_DOKON_TURI, KLIENT_DISTRIBUTOR, KLIENT_AGENT_KOD,
    KLIENT_CHASTOTA, KLIENT_LIMIT, KLIENT_CONFIRM,
    KLIENT_EDIT_VALUE,
    SOROV_TUR, SOROV_DOKON, SOROV_LOK, SOROV_TEL,
    SOROV_FOTO, SOROV_IZOH, SOROV_CONFIRM,
    SOROV_BATCH_COLLECT, SOROV_BATCH_PREVIEW,
    LIMIT_DOKON, LIMIT_SUMMA,
    INSTR_MATN, ADD_ADMIN_ID,
)
print("config imported OK", flush=True)

from database import init_db
print("database imported OK", flush=True)

from utils import daily_report_job, weekly_report_job, agent_reminder_job, pending_sorovlar_alert_job
print("utils imported OK", flush=True)

from handlers import (
    reaction_handler,
    cancel, start,
    ism_olish, lavozim_olish, kod_olish,
    filial_olish, telefon_olish, telefon2_olish,
    tugilgan_kun_olish,
    xodim_chat_handler,
    admin_guruh_javob,
    callback_handler,
    admin_statistika, admin_xodimlar,
    admin_kutilayotganlar, admin_bloklanganlar,
    admin_excel_eksport,
    search_query_handler,
    admin_biriktirish,
    biriktir_list_cb, biriktir_new_cb, biriktir_agent_cb, biriktir_back_cb,
    biriktir_change_cb, biriktir_rm_cb, biriktir_block_cb,
    biriktir_edit_field_cb, biriktir_edit_value_handler,
    biriktir_checker_cb,
    edit_field, edit_value,
    _xodim_list_page_cb, _xodim_info_cb, _xodim_edit_cb, _xodim_search_start_cb,
    new_client_command, klient_rasm, klient_firma_nomi, klient_telefon1,
    klient_telefon2, klient_inn, klient_orienter,
    klient_lokatsiya, klient_lokatsiya_hint,
    klient_kategoriya, klient_dokon_turi, klient_distributor, klient_agent_kod,
    klient_chastota,
    klient_limit, klient_confirm, klient_edit_value,
    admin_klientlar,
    klient_reject_reason,
    admin_tarix, tarix_filter_callback,
    topic_closed_handler,
    admin_upload_db,
    add_admin_command, add_admin_id_receive, admin_mgmt_callback,
    instruksiya_cmd,
    admin_instruksiya_lavozim_cb,
    admin_instruksiya_edit_cb,
    admin_instruksiya_del_cb,
    admin_instruksiya_matn_save,
    faq_start, faq_callback,
    matn_javob_handler,
)
from handlers.menu_dispatch import BuyruqFilter
print("handlers imported OK", flush=True)

from sorov_handlers import (
    sorov_start, sorov_tur_olish,
    sorov_dokon_olish, sorov_dokon_foto_olish, sorov_lok_olish, sorov_tel_olish,
    sorov_foto_olish, sorov_izoh_olish, sorov_confirm_callback,
    batch_collect_handler, batch_callback,
    sorov_sup_callback,
    limit_start, limit_dokon_olish, limit_summa_olish,
)
print("sorov_handlers imported OK", flush=True)
print("=== ALL IMPORTS DONE ===", flush=True)

# ── Logging: console + file ───────────────────────────────────────
from logging.handlers import RotatingFileHandler
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        RotatingFileHandler("bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def build_application() -> Application:
    persistence = PicklePersistence(filepath="bot_persistence.pkl")
    app = Application.builder().token(TOKEN).persistence(persistence).build()

    start_cmd = CommandHandler("start", start)

    # ── Ro'yxatdan o'tish ConversationHandler ────────────────────
    royxat_conv = ConversationHandler(
        entry_points=[start_cmd],
        states={
            ISM:          [MessageHandler(filters.TEXT & ~filters.COMMAND, ism_olish)],
            LAVOZIM:      [MessageHandler(filters.TEXT & ~filters.COMMAND, lavozim_olish)],
            KOD:          [MessageHandler(filters.TEXT & ~filters.COMMAND, kod_olish)],
            FILIAL:       [MessageHandler(filters.TEXT & ~filters.COMMAND, filial_olish)],
            TELEFON:      [
                MessageHandler(filters.CONTACT, telefon_olish),
                MessageHandler(filters.TEXT & ~filters.COMMAND, telefon_olish),
            ],
            TELEFON2:     [
                MessageHandler(filters.CONTACT, telefon2_olish),
                MessageHandler(filters.TEXT & ~filters.COMMAND, telefon2_olish),
            ],
            TUGILGAN_KUN: [MessageHandler(filters.TEXT & ~filters.COMMAND, tugilgan_kun_olish)],
        },
        fallbacks=[start_cmd],
        allow_reentry=True,
    )

    # ── Unified Employee Management ConversationHandler ──────────────
    xodim_mgmt_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^👥 Xodimlar$"), admin_xodimlar)],
        states={
            XODIM_LIST: [
                CallbackQueryHandler(_xodim_edit_cb, pattern="^xodim_edit_"),
                CallbackQueryHandler(_xodim_list_page_cb, pattern="^xodim_list_page_"),
                CallbackQueryHandler(_xodim_info_cb, pattern="^xodim_info_"),
                CallbackQueryHandler(_xodim_search_start_cb, pattern="^xodim_search_start$"),
            ],
            EDIT_FIELD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field),
            ],
            EDIT_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value),
            ],
            SEARCH_QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_query_handler),
            ],
        },
        fallbacks=[start_cmd],
        allow_reentry=True,
        per_message=False,
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
        fallbacks=[start_cmd],
        allow_reentry=True,
        per_message=False,
    )

    # ── Klient registratsiya ConversationHandler (16 qadam) ──────
    _klient_f = BuyruqFilter("yangi_klient", defaults=("🏪 Yangi Klient",))
    _dokon_f  = BuyruqFilter("dokon_qoshish", defaults=("🏪 Dokon qo'shish",))
    klient_conv = ConversationHandler(
        entry_points=[
            MessageHandler(_klient_f | _dokon_f, new_client_command),
            CommandHandler("new_client", new_client_command),
        ],
        states={
            KLIENT_RASM:        [
                MessageHandler(filters.PHOTO, klient_rasm),
                MessageHandler(filters.TEXT & ~filters.COMMAND, klient_rasm),
            ],
            KLIENT_FIRMA_NOMI:  [MessageHandler(filters.TEXT & ~filters.COMMAND, klient_firma_nomi)],
            KLIENT_TELEFON1:    [MessageHandler(filters.TEXT & ~filters.COMMAND, klient_telefon1)],
            KLIENT_TELEFON2:    [MessageHandler(filters.TEXT & ~filters.COMMAND, klient_telefon2)],
            KLIENT_INN:         [MessageHandler(filters.TEXT & ~filters.COMMAND, klient_inn)],
            KLIENT_ORIENTER:    [MessageHandler(filters.TEXT & ~filters.COMMAND, klient_orienter)],
            KLIENT_LOKATSIYA:   [
                MessageHandler(filters.LOCATION, klient_lokatsiya),
                MessageHandler(filters.TEXT & ~filters.COMMAND, klient_lokatsiya),
                CallbackQueryHandler(klient_lokatsiya_hint, pattern="^lok_gps$|^lok_text$"),
            ],
            KLIENT_KATEGORIYA:  [CallbackQueryHandler(klient_kategoriya, pattern="^klient_kat_")],
            KLIENT_DOKON_TURI:  [CallbackQueryHandler(klient_dokon_turi, pattern="^klient_tur_")],
            KLIENT_DISTRIBUTOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, klient_distributor)],
            KLIENT_AGENT_KOD:   [MessageHandler(filters.TEXT & ~filters.COMMAND, klient_agent_kod)],
            KLIENT_CHASTOTA:    [CallbackQueryHandler(klient_chastota, pattern="^klient_chas_")],
            KLIENT_LIMIT:       [MessageHandler(filters.TEXT & ~filters.COMMAND, klient_limit)],
            KLIENT_CONFIRM:     [CallbackQueryHandler(klient_confirm, pattern="^klient_submit$|^klient_cancel$|^klient_edit$|^klient_edit_back$|^klient_ef_")],
            KLIENT_EDIT_VALUE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, klient_edit_value)],
        },
        fallbacks=[start_cmd],
        allow_reentry=True,
        per_message=False,
    )

    # ── So'rov ConversationHandler (agent/FR/supervisor requests) ──
    _sorov_f = BuyruqFilter("sorov", defaults=("❓ So'rov", "📝 Muammo yozish"))
    sorov_conv = ConversationHandler(
        entry_points=[MessageHandler(_sorov_f, sorov_start)],
        states={
            SOROV_TUR:  [CallbackQueryHandler(sorov_tur_olish, pattern="^sorov_tur_")],
            SOROV_DOKON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, sorov_dokon_olish),
                MessageHandler(filters.PHOTO, sorov_dokon_foto_olish),
            ],
            SOROV_LOK:  [MessageHandler(filters.LOCATION, sorov_lok_olish)],
            SOROV_TEL:  [MessageHandler(filters.TEXT & ~filters.COMMAND, sorov_tel_olish)],
            SOROV_FOTO: [MessageHandler(filters.PHOTO, sorov_foto_olish)],
            SOROV_IZOH: [MessageHandler(filters.TEXT & ~filters.COMMAND, sorov_izoh_olish)],
            SOROV_BATCH_COLLECT: [MessageHandler(filters.ALL & ~filters.COMMAND, batch_collect_handler)],
            SOROV_BATCH_PREVIEW: [CallbackQueryHandler(batch_callback, pattern="^batch_")],
            SOROV_CONFIRM: [CallbackQueryHandler(sorov_confirm_callback, pattern="^sorov_confirm_")],
        },
        fallbacks=[start_cmd],
        allow_reentry=True,
        per_message=False,
    )

    # ── Limit qo'shish ConversationHandler (Filial Rahbari) ─────
    _limit_f = BuyruqFilter("limit", defaults=("💰 Limit qo'shish",))
    limit_conv = ConversationHandler(
        entry_points=[MessageHandler(_limit_f, limit_start)],
        states={
            LIMIT_DOKON: [MessageHandler(filters.TEXT & ~filters.COMMAND, limit_dokon_olish)],
            LIMIT_SUMMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, limit_summa_olish)],
        },
        fallbacks=[start_cmd],
        allow_reentry=True,
        per_message=False,
    )

    instr_conv = ConversationHandler(
        entry_points=[CommandHandler("instruksiya", instruksiya_cmd)],
        states={
            INSTR_MATN: [
                CallbackQueryHandler(admin_instruksiya_lavozim_cb, pattern=r"^instr_lav_"),
                CallbackQueryHandler(admin_instruksiya_edit_cb,    pattern=r"^instr_edit_"),
                CallbackQueryHandler(admin_instruksiya_del_cb,     pattern=r"^instr_del_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_instruksiya_matn_save),
                MessageHandler(filters.PHOTO, admin_instruksiya_matn_save),
                MessageHandler(filters.VIDEO, admin_instruksiya_matn_save),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        per_message=False,
    )

    app.add_handler(royxat_conv)
    app.add_handler(xodim_mgmt_conv)
    app.add_handler(biriktir_conv)
    app.add_handler(klient_conv)
    app.add_handler(sorov_conv)
    app.add_handler(limit_conv)
    app.add_handler(instr_conv)

    app.add_handler(MessageHandler(filters.Regex(r"^📋 Tarix$"),                   admin_tarix))
    app.add_handler(MessageHandler(filters.Regex(r"^📊 Statistika$"),             admin_statistika))
    app.add_handler(MessageHandler(filters.Regex(r"^⏳ Kutilayotgan so'rovlar$"), admin_kutilayotganlar))
    app.add_handler(MessageHandler(filters.Regex(r"^🚫 Bloklanganlar$"),          admin_bloklanganlar))
    app.add_handler(MessageHandler(filters.Regex(r"^📥 Excel$"),                  admin_excel_eksport))
    # ── Admin qo'shish ConversationHandler ──────────────────────────
    add_admin_conv = ConversationHandler(
        entry_points=[CommandHandler("add_admin", add_admin_command)],
        states={
            ADD_ADMIN_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_id_receive),
                CallbackQueryHandler(admin_mgmt_callback, pattern="^admin_rm_|^admin_add$|^admin_noop$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(add_admin_conv)

    app.add_handler(CommandHandler("upload_db",   admin_upload_db))
    app.add_handler(MessageHandler(
        filters.Document.FileExtension("db"),
        admin_upload_db,
    ))
    app.add_handler(CommandHandler("klientlar",  admin_klientlar))
    app.add_handler(MessageReactionHandler(reaction_handler))

    # Topic o'chirilganda xodimni bazadan o'chirish
    app.add_handler(MessageHandler(
        filters.Chat(GROUP_CHAT_ID) & filters.StatusUpdate.FORUM_TOPIC_CLOSED,
        topic_closed_handler,
    ))

    _faq_f       = BuyruqFilter("faq", defaults=("📋 FAQ",))
    _matn_javob_f = BuyruqFilter("matn_javob")
    app.add_handler(MessageHandler(_faq_f, faq_start))
    app.add_handler(MessageHandler(_matn_javob_f, matn_javob_handler))
    app.add_handler(CallbackQueryHandler(sorov_sup_callback, pattern=r"^sorov_appr_|^sorov_rej_|^sorov_done_|^sorov_rad_"))
    app.add_handler(CallbackQueryHandler(tarix_filter_callback, pattern=r"^tarix_[fd]_"))
    app.add_handler(CallbackQueryHandler(batch_callback, pattern=r"^batch_"))
    app.add_handler(CallbackQueryHandler(faq_callback, pattern=r"^faq_"))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Chat(GROUP_CHAT_ID) & ~filters.COMMAND, admin_guruh_javob))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, xodim_chat_handler))

    # Admin private handler (group 1): reply routing, klient rad, klient qidirish, sorov javob
    # TEXT cheklovi yo'q — admin foto/video reply ham xodimga yo'naltiriladi
    app.add_handler(
        MessageHandler(
            ~filters.Chat(GROUP_CHAT_ID) & ~filters.COMMAND,
            klient_reject_reason,
        ),
        group=1,
    )

    return app


async def _apply_slash_commands(bot) -> None:
    """DB dagi BotSlashBuyruq lardan Telegram slash buyruqlarini yangilaydi."""
    from telegram import BotCommandScopeDefault, BotCommandScopeChat
    from database import get_all_slash_buyruqlar
    from config import ADMIN_ID as _ADMIN_ID

    try:
        buyruqlar = await get_all_slash_buyruqlar()
    except Exception as e:
        logger.warning(f"Slash buyruqlarni DBdan olishda xato: {e}")
        buyruqlar = []

    # Scope bo'yicha ajratish
    default_cmds: list[BotCommand] = []
    extra_admin:  list[BotCommand] = []

    for b in buyruqlar:
        cmd = BotCommand(b.buyruq, b.tavsif)
        if b.lavozim == "admin":
            extra_admin.append(cmd)
        else:
            default_cmds.append(cmd)

    # Admin hamma buyruqlarni ko'radi: umumiy + admin-only
    admin_cmds = default_cmds + extra_admin

    # Fallback: DB bo'sh bo'lsa ham /start doim bo'lsin
    if not default_cmds:
        default_cmds = [
            BotCommand("start",       "Botni qayta ishga tushirish"),
            BotCommand("instruksiya", "Botdan foydalanish yo'riqnomasi"),
        ]
    if not admin_cmds:
        admin_cmds = [
            BotCommand("start",       "Botni qayta ishga tushirish"),
            BotCommand("instruksiya", "Botdan foydalanish yo'riqnomasi"),
            BotCommand("new_client",  "Yangi klient registratsiyasi"),
            BotCommand("klientlar",   "Klientlar ro'yxati"),
            BotCommand("add_admin",   "Yangi admin qo'shish"),
        ]

    await bot.set_my_commands(default_cmds, scope=BotCommandScopeDefault())
    await bot.set_my_commands(admin_cmds,   scope=BotCommandScopeChat(chat_id=_ADMIN_ID))
    logger.info(f"✅ Slash buyruqlar yangilandi: {len(default_cmds)} umumiy, {len(admin_cmds)} admin.")


async def refresh_menus_job(context) -> None:
    """Har 30 soniyada DB dan menyu keshi va slash buyruqlarni yangilaydi."""
    from database import get_all_active_tugmalar
    from handlers.menu_dispatch import refresh_menu_cache
    try:
        tugmalar = await get_all_active_tugmalar()
        refresh_menu_cache(tugmalar)
        await _apply_slash_commands(context.bot)
    except Exception as e:
        logger.warning(f"[refresh_menus_job] xato: {e}")


async def post_init(app: Application):
    await init_db()
    logger.info("✅ Ma'lumotlar bazasi tayyor.")

    # ── Bot menyu keshi + slash buyruqlarini yuklash ──────────────────────────
    try:
        from database import get_all_active_tugmalar
        from handlers.menu_dispatch import refresh_menu_cache
        tugmalar = await get_all_active_tugmalar()
        refresh_menu_cache(tugmalar)
        logger.info(f"✅ Bot menyu keshi yuklandi: {len(tugmalar)} ta tugma.")
    except Exception as e:
        logger.warning(f"Bot menyu keshini yuklashda xato: {e}")

    await _apply_slash_commands(app.bot)
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

    app.job_queue.run_repeating(
        pending_sorovlar_alert_job,
        interval=300,
        first=300,
    )
    logger.info("✅ Kutilayotgan so'rovlar tekshiruvi rejalashtirildi: har 5 daqiqa")

    # Menyu keshi + slash buyruqlarini har 30 soniyada yangilash
    app.job_queue.run_repeating(
        refresh_menus_job,
        interval=30,
        first=30,
    )
    logger.info("✅ Menyu avtomatik yangilanishi rejalashtirildi: har 30 soniya")


async def error_handler(update: object, context) -> None:
    from telegram.error import NetworkError, TimedOut, Conflict
    from config import ADMIN_ID as _ADMIN

    if isinstance(context.error, (NetworkError, TimedOut, Conflict)):
        logger.warning(f"Tarmoq xatosi (vaqtinchalik): {context.error}")
        return

    logger.error("Kutilmagan xato:", exc_info=context.error)

    # Foydalanuvchiga o'zbek tilida xato xabari
    if update and hasattr(update, "effective_user") and update.effective_user:
        try:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text="⚠️ Texnik xato yuz berdi. Iltimos /start bosing va qaytadan urinib ko'ring.",
            )
        except Exception:
            pass

    # Adminga batafsil xato xabari
    try:
        err_text = str(context.error)[:800]
        await context.bot.send_message(
            chat_id=_ADMIN,
            text=f"🔴 *Bot xatosi yuz berdi*\n\n`{err_text}`",
            parse_mode="Markdown",
        )
    except Exception:
        pass


def main():
    # Bir vaqtda faqat bitta instance ishlashi uchun PID lock
    _pid_file = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.pid"), "w")
    try:
        fcntl.flock(_pid_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        logger.error("Bot allaqachon ishlamoqda! Ikkinchi instance ishga tushmaydi.")
        sys.exit(1)

    logger.info("🚀 Dusel Company boti ishga tushmoqda...")
    app = build_application()
    app.post_init = post_init
    app.add_error_handler(error_handler)

    if WEBHOOK_URL:
        logger.info(f"🌐 Webhook rejimi: {WEBHOOK_URL}  port={PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TOKEN}",
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        logger.info("🔄 Polling rejimi (lokalda ishlatish uchun)")
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )


if __name__ == "__main__":
    try:
        print("=== CALLING main() ===", flush=True)
        main()
    except Exception as exc:
        print(f"CRITICAL ERROR: {exc}", flush=True)
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        sys.exit(1)
