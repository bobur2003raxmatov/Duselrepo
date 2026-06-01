"""Xodimlar, Xabarlar, XabarGuruhi admin."""

from django.contrib import admin
from django.utils.html import format_html
from ..models import Xodim, Xabar, XabarGuruhi


@admin.register(Xodim)
class XodimAdmin(admin.ModelAdmin):
    list_display   = ("user_id", "ism", "lavozim", "filial", "kod", "topic_id_display", "status", "sana")
    list_filter    = ("status", "lavozim", "filial")
    search_fields  = ("ism", "kod", "filial", "user_id")
    ordering       = ("-sana",)
    list_per_page  = 25
    actions        = ["approve_xodim", "block_xodim"]

    def topic_id_display(self, obj):
        if obj.topic_id:
            return obj.topic_id
        return format_html('<span style="color:red;font-weight:bold">—</span>')
    topic_id_display.short_description = "Topic ID"

    @admin.action(description="✅ Tanlangan xodimlarni tasdiqlash")
    def approve_xodim(self, request, queryset):
        n = queryset.filter(status="pending").update(status="approved")
        self.message_user(request, f"{n} ta xodim tasdiqlandi.")

    @admin.action(description="🚫 Tanlangan xodimlarni bloklash")
    def block_xodim(self, request, queryset):
        n = queryset.exclude(status="blocked").update(status="blocked")
        self.message_user(request, f"{n} ta xodim bloklandi.")


@admin.register(Xabar)
class XabarAdmin(admin.ModelAdmin):
    list_display  = ("id", "xodim_name", "filial", "xabar_turi", "holat", "vaqt")
    list_filter   = ("holat", "filial", "xabar_turi")
    search_fields = ("xodim_name", "filial")
    ordering      = ("-id",)
    list_per_page = 25


@admin.register(XabarGuruhi)
class XabarGuruhiAdmin(admin.ModelAdmin):
    list_display  = ("id", "ism", "filial", "holat", "urgency", "vaqt", "javob_vaqt")
    list_filter   = ("holat", "urgency", "filial")
    search_fields = ("ism", "filial")
    ordering      = ("-id",)
    list_per_page = 25
