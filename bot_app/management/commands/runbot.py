"""
python manage.py runbot

Bot'ni polling yoki webhook rejimda ishga tushiradi.
Jadvallar avval yaratilgan bo'lishi kerak:
    python manage.py migrate             # yangi DB uchun
    python manage.py migrate --fake-initial  # mavjud DB uchun
"""
import asyncio
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Dusel Company Telegram bot'ini ishga tushiradi"

    def add_arguments(self, parser):
        parser.add_argument(
            "--migrate",
            action="store_true",
            help="Botdan oldin migrate buyrug'ini avtomatik bajaradi",
        )
        parser.add_argument(
            "--fake-initial",
            action="store_true",
            dest="fake_initial",
            help="Mavjud DB uchun --fake-initial bilan migrate bajaradi",
        )

    def handle(self, *args, **options):
        if options["migrate"] or options["fake_initial"]:
            from django.core.management import call_command
            if options["fake_initial"]:
                self.stdout.write("⚙️  migrate --fake-initial bajarilmoqda...")
                call_command("migrate", fake_initial=True, verbosity=1)
            else:
                self.stdout.write("⚙️  migrate bajarilmoqda...")
                call_command("migrate", verbosity=1)

        from database import init_db
        from config import WEBHOOK_URL, TOKEN
        from bot import build_application, post_init, error_handler

        # Async init (db cache yuklash) yangi loop da
        asyncio.run(init_db())

        app = build_application()
        app.post_init = post_init
        app.add_error_handler(error_handler)

        if WEBHOOK_URL:
            # Webhook rejimi: bot initialize qilinadi, Django view so'rovlarni qabul qiladi
            asyncio.run(self._setup_webhook(app, TOKEN, WEBHOOK_URL))
            self.stdout.write("🌐 Webhook sozlandi. Django serverni ishga tushiring:")
            self.stdout.write("   gunicorn dusel.wsgi  yoki  uvicorn dusel.asgi:application")
        else:
            # Polling rejimi: run_polling o'z event loop ini boshqaradi (sync chaqiruv)
            self.stdout.write("🔄 Polling rejimida ishlamoqda (Ctrl+C bilan to'xtatish)")
            app.run_polling(
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "message_reaction",
                                 "chat_member", "my_chat_member"],
            )

    async def _setup_webhook(self, app, token, webhook_url):
        from bot_app.views import set_bot_app
        await app.initialize()
        await app.start()
        set_bot_app(app)
        full_url = f"{webhook_url}/webhook/{token}/"
        await app.bot.set_webhook(full_url, drop_pending_updates=True)
        logger.info(f"🌐 Webhook o'rnatildi: {full_url}")
        self.stdout.write(f"🌐 Webhook: {full_url}")
