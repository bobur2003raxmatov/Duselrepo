"""Tizim ma'lumotlari: Harakatlar (AuditLog), Adminlar, SupervisorGroup, Instruksiya va boshqalar."""

from django.contrib import admin
from django.utils.html import format_html
from ..models import AuditLog, AdminUser, SupervisorGroup, Instruksiya, Biriktirish, CheckerFaollik, Baholash, AdminMsgMap
from ._constants import ACTION_LABELS, ACTION_TO_KAT, ROLE_LABELS, STATUS_COLORS
from ._filters import KategoriyaFilter, RoleFilter


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display    = ("id", "kategoriya_display", "harakat_display", "lavozim_display", "target", "holat_display", "created_at")
    list_filter     = (KategoriyaFilter, RoleFilter, "status")
    search_fields   = ("user_id", "action_type", "target", "new_value")
    ordering        = ("-id",)
    readonly_fields = ("created_at", "user_id", "user_role", "action_type", "target", "old_value", "new_value", "status", "request_id")
    date_hierarchy  = "created_at"
    list_per_page   = 30

    _KAT_COLORS = {
        "So'rovlar": "#0d6efd", "Supervisor": "#6f42c1",
        "Klientlar": "#198754", "Limit": "#fd7e14", "Xodimlar": "#dc3545",
    }

    def kategoriya_display(self, obj):
        kat   = ACTION_TO_KAT.get(obj.action_type, "Boshqa")
        color = self._KAT_COLORS.get(kat, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>',
            color, kat,
        )
    kategoriya_display.short_description = "Kategoriya"

    def harakat_display(self, obj):
        return ACTION_LABELS.get(obj.action_type, obj.action_type or "—")
    harakat_display.short_description = "Harakat"

    def lavozim_display(self, obj):
        return ROLE_LABELS.get(obj.user_role, obj.user_role or "—")
    lavozim_display.short_description = "Lavozim"

    def holat_display(self, obj):
        if not obj.status:
            return "—"
        color = STATUS_COLORS.get(obj.status, "#6c757d")
        return format_html('<span style="color:{};font-weight:bold">{}</span>', color, obj.status)
    holat_display.short_description = "Holat"


@admin.register(AdminUser)
class AdminUserAdmin(admin.ModelAdmin):
    list_display  = ("user_id",)
    list_per_page = 25


@admin.register(SupervisorGroup)
class SupervisorGroupAdmin(admin.ModelAdmin):
    list_display  = ("supervisor_id", "group_chat_id")
    list_per_page = 25


@admin.register(Instruksiya)
class InstruksiyaAdmin(admin.ModelAdmin):
    list_display  = ("lavozim", "media_type", "updated_at")
    search_fields = ("lavozim",)
    list_per_page = 25


@admin.register(Biriktirish)
class BiriktirishAdmin(admin.ModelAdmin):
    list_display  = ("agent_id", "checker_id")
    search_fields = ("agent_id", "checker_id")
    list_per_page = 25


@admin.register(CheckerFaollik)
class CheckerFaollikAdmin(admin.ModelAdmin):
    list_display  = ("checker_id", "last_active")
    list_per_page = 25


@admin.register(Baholash)
class BaholashAdmin(admin.ModelAdmin):
    list_display  = ("id", "group_id", "agent_id", "checker_id", "yulduz", "vaqt")
    list_filter   = ("yulduz",)
    ordering      = ("-id",)
    list_per_page = 25


@admin.register(AdminMsgMap)
class AdminMsgMapAdmin(admin.ModelAdmin):
    list_display  = ("id", "user_id", "group_msg_id", "private_msg_id")
    search_fields = ("user_id",)
    ordering      = ("-id",)
    list_per_page = 25
