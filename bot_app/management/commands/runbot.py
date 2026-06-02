"""
python manage.py runbot

Django orqali bot webhook'ini sozlaydi.
Bot so'rovlarni Django (uWSGI/gunicorn) orqali qabul qiladi.

Ishlatishdan oldin:
    python manage.py migrate
"""
import asyncio
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Dusel bot webhook'ini sozlaydi (Django webhook rejimi)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--migrate",
            action="store_true",
            help="Botdan oldin migrate buyrug'ini avtomatik bajaradi",
        )

    def handle(self, *args, **options):
        if options["migrate"]:
            from django.core.management import call_command
            self.stdout.write("⚙️  migrate bajarilmoqda...")
            call_command("migrate", verbosity=1)

        from config import WEBHOOK_URL, TOKEN
        if not WEBHOOK_URL:
            self.stderr.write("❌ WEBHOOK_URL o'rnatilmagan. .env faylini tekshiring.")
            return

        from bot import build_application, post_init, error_handler
        app = build_application(webhook_mode=True, post_init_cb=post_init)
        app.add_error_handler(error_handler)

        asyncio.run(self._setup_webhook(app, TOKEN, WEBHOOK_URL))
        self.stdout.write("✅ Webhook sozlandi. Django serverni ishga tushiring.")

    async def _setup_webhook(self, app, token, webhook_url):
        await app.initialize()
        await app.start()
        full_url = f"{webhook_url.rstrip('/')}/webhook/{token}/"
        await app.bot.set_webhook(full_url, drop_pending_updates=True)
        self.stdout.write(f"🌐 Webhook: {full_url}")
        await app.stop()
        await app.shutdown()
