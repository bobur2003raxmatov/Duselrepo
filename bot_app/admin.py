from django.contrib import admin
from .models import (
    Xodim, Xabar, XabarGuruhi, FaqKategoriya, Faq,
    Baholash, CheckerFaollik, Biriktirish, AdminMsgMap,
    Klient, Sorov, SupervisorGroup, AdminUser, AuditLog, Instruksiya,
)


@admin.register(Xodim)
class XodimAdmin(admin.ModelAdmin):
    list_display = ("user_id", "ism", "lavozim", "filial", "kod", "status", "sana")
    list_filter = ("status", "lavozim", "filial")
    search_fields = ("ism", "kod", "filial", "user_id")
    ordering = ("-sana",)


@admin.register(Xabar)
class XabarAdmin(admin.ModelAdmin):
    list_display = ("id", "xodim_name", "filial", "xabar_turi", "holat", "vaqt")
    list_filter = ("holat", "filial", "xabar_turi")
    search_fields = ("xodim_name", "filial")
    ordering = ("-id",)


@admin.register(XabarGuruhi)
class XabarGuruhiAdmin(admin.ModelAdmin):
    list_display = ("id", "ism", "filial", "holat", "urgency", "vaqt", "javob_vaqt")
    list_filter = ("holat", "urgency", "filial")
    search_fields = ("ism", "filial")
    ordering = ("-id",)


@admin.register(FaqKategoriya)
class FaqKategoriyaAdmin(admin.ModelAdmin):
    list_display = ("id", "emoji", "nomi", "tartib")
    ordering = ("tartib", "id")


@admin.register(Faq)
class FaqAdmin(admin.ModelAdmin):
    list_display = ("id", "kategoriya", "savol", "tartib")
    list_filter = ("kategoriya",)
    search_fields = ("savol", "javob")
    ordering = ("kategoriya", "tartib", "id")


@admin.register(Baholash)
class BalholashAdmin(admin.ModelAdmin):
    list_display = ("id", "group_id", "agent_id", "checker_id", "yulduz", "vaqt")
    list_filter = ("yulduz",)
    ordering = ("-id",)


@admin.register(CheckerFaollik)
class CheckerFaollikAdmin(admin.ModelAdmin):
    list_display = ("checker_id", "last_active")


@admin.register(Biriktirish)
class BiriktirishAdmin(admin.ModelAdmin):
    list_display = ("agent_id", "checker_id")
    search_fields = ("agent_id", "checker_id")


@admin.register(Klient)
class KlientAdmin(admin.ModelAdmin):
    list_display = (
        "id", "firma_nomi", "telefon1", "distributor",
        "agent_kod", "kategoriya", "status", "sana",
    )
    list_filter = ("status", "kategoriya", "dokon_turi", "distributor")
    search_fields = ("firma_nomi", "telefon1", "inn", "agent_kod", "distributor")
    ordering = ("-id",)


@admin.register(Sorov)
class SorovAdmin(admin.ModelAdmin):
    list_display = ("id", "agent_ism", "tur", "dokon_nomi", "status", "sana")
    list_filter = ("status", "tur")
    search_fields = ("agent_ism", "dokon_nomi")
    ordering = ("-id",)


@admin.register(SupervisorGroup)
class SupervisorGroupAdmin(admin.ModelAdmin):
    list_display = ("supervisor_id", "group_chat_id")


@admin.register(AdminUser)
class AdminUserAdmin(admin.ModelAdmin):
    list_display = ("user_id",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "user_role", "action_type", "target", "status", "created_at")
    list_filter = ("user_role", "status", "action_type")
    search_fields = ("user_id", "action_type", "target")
    ordering = ("-id",)
    readonly_fields = ("created_at",)


@admin.register(Instruksiya)
class InstruksiyaAdmin(admin.ModelAdmin):
    list_display = ("lavozim", "media_type", "updated_at")
    search_fields = ("lavozim",)


admin.site.site_header = "Dusel Company Bot — Admin"
admin.site.site_title = "Dusel Bot Admin"
admin.site.index_title = "Boshqaruv paneli"
