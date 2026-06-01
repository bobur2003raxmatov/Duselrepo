"""Klientlar va So'rovlar admin."""

from django.contrib import admin
from django.utils.html import format_html
from ..models import Klient, Sorov


@admin.register(Klient)
class KlientAdmin(admin.ModelAdmin):
    list_display  = ("id", "firma_nomi", "telefon1", "distributor", "agent_kod", "kategoriya", "status", "lokatsiya_display", "sana")
    list_filter   = ("status", "kategoriya", "dokon_turi", "distributor")
    search_fields = ("firma_nomi", "telefon1", "inn", "agent_kod", "distributor")
    ordering      = ("-id",)
    list_per_page = 25

    def lokatsiya_display(self, obj):
        if obj.lokatsiya_lat is not None and obj.lokatsiya_lon is not None:
            url = f"https://maps.google.com/?q={obj.lokatsiya_lat},{obj.lokatsiya_lon}"
            return format_html(
                '<a href="{}" target="_blank">📍 {:.4f}, {:.4f}</a>',
                url, obj.lokatsiya_lat, obj.lokatsiya_lon,
            )
        return obj.lokatsiya_address or "—"
    lokatsiya_display.short_description = "Lokatsiya"


@admin.register(Sorov)
class SorovAdmin(admin.ModelAdmin):
    list_display  = ("id", "agent_ism", "tur", "dokon_nomi", "status_display", "display_photos", "sana")
    list_filter   = (("status", admin.ChoicesFieldListFilter), "tur")
    search_fields = ("agent_ism", "dokon_nomi")
    ordering      = ("-id",)
    list_per_page = 25

    _STATUS_ICONS = {
        "pending_supervisor": "⏳", "pending_admin": "⏳",
        "approved": "✅", "rejected": "❌",
    }

    def status_display(self, obj):
        icon = self._STATUS_ICONS.get(obj.status, "❓")
        return format_html("{} {}", icon, obj.status)
    status_display.short_description = "Holat"

    def display_photos(self, obj):
        if not obj.foto_ids:
            return "—"
        ids = [x for x in obj.foto_ids.split(",") if x.strip()]
        return f"📷 {len(ids)} ta" if ids else "—"
    display_photos.short_description = "Rasmlar"
