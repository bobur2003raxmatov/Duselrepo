"""
Bot menyular va FAQ admin.

Bu faylda bot tugmalarini qo'shish, o'zgartirish va o'chirish boshqariladi.
O'zgarishlar 30 soniya ichida botga avtomatik yuklanadi.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from ..models import BotMenuRol, BotTugma, BotSlashBuyruq, FaqKategoriya, Faq


# ── Bot menyular ──────────────────────────────────────────────────────────────

class BotTugmaInline(admin.TabularInline):
    model    = BotTugma
    extra    = 0
    fields   = ("matn", "buyruq", "qator", "ustun", "faol")
    ordering = ("qator", "ustun")

    def get_extra(self, request, obj=None, **kwargs):
        return 0 if obj and obj.tugmalar.exists() else 1


@admin.register(BotMenuRol)
class BotMenuRolAdmin(admin.ModelAdmin):
    list_display  = ("lavozim", "tugmalar_display", "faol")
    list_filter   = ("faol",)
    inlines       = [BotTugmaInline]
    list_per_page = 25

    def tugmalar_display(self, obj):
        tugmalar = list(obj.tugmalar.filter(faol=True).order_by("qator", "ustun"))
        if not tugmalar:
            return format_html('<span style="color:#aaa">—</span>')
        rows: dict[int, list] = {}
        for t in tugmalar:
            rows.setdefault(t.qator, []).append(t.matn)
        parts = [
            " | ".join(
                f'<span style="background:#0d6efd;color:#fff;padding:1px 7px;'
                f'border-radius:8px;font-size:11px">{m}</span>'
                for m in rows[r]
            )
            for r in sorted(rows)
        ]
        return mark_safe(" &nbsp;→&nbsp; ".join(parts))
    tugmalar_display.short_description = "Tugmalar (qatorlar bo'yicha)"


@admin.register(BotTugma)
class BotTugmaAdmin(admin.ModelAdmin):
    list_display  = ("rol", "matn_display", "buyruq_display", "qator", "ustun", "faol")
    list_filter   = ("rol", "buyruq", "faol")
    search_fields = ("matn",)
    list_editable = ("faol",)
    list_per_page = 50
    ordering      = ("rol", "qator", "ustun")

    def matn_display(self, obj):
        return format_html(
            '<span style="background:#198754;color:#fff;padding:2px 10px;border-radius:10px">{}</span>',
            obj.matn,
        )
    matn_display.short_description = "Tugma matni"

    def buyruq_display(self, obj):
        return dict(BotTugma.BUYRUQ_CHOICES).get(obj.buyruq, obj.buyruq)
    buyruq_display.short_description = "Buyruq"


# ── Slash buyruqlar ──────────────────────────────────────────────────────────

@admin.register(BotSlashBuyruq)
class BotSlashBuyruqAdmin(admin.ModelAdmin):
    list_display  = ("buyruq_display", "tavsif", "lavozim_display", "tartib", "faol")
    list_filter   = ("faol", "lavozim")
    list_editable = ("faol", "tartib")
    ordering      = ("tartib", "buyruq")
    list_per_page = 50

    def buyruq_display(self, obj):
        return format_html(
            '<code style="background:#f1f1f1;padding:2px 8px;border-radius:4px">/{}</code>',
            obj.buyruq,
        )
    buyruq_display.short_description = "Buyruq"

    def lavozim_display(self, obj):
        if not obj.lavozim:
            return format_html('<span style="color:#198754">Barcha</span>')
        return obj.lavozim
    lavozim_display.short_description = "Ko'ruvchi"


# ── FAQ ───────────────────────────────────────────────────────────────────────

@admin.register(FaqKategoriya)
class FaqKategoriyaAdmin(admin.ModelAdmin):
    list_display  = ("id", "emoji", "nomi", "tartib")
    ordering      = ("tartib", "id")
    list_per_page = 25


@admin.register(Faq)
class FaqAdmin(admin.ModelAdmin):
    list_display  = ("id", "kategoriya", "savol", "tartib")
    list_filter   = ("kategoriya",)
    search_fields = ("savol", "javob")
    ordering      = ("kategoriya", "tartib", "id")
    list_per_page = 25
