"""
bot_app/admin/ — Admin panel bo'limlari.

Fayllar:
  _constants.py  — Umumiy konstantalar (ACTION_LABELS, ROLE_LABELS, ...)
  _filters.py    — Qayta ishlatiladigan filterlar
  xodimlar.py    — Xodim, Xabar, XabarGuruhi
  klientlar.py   — Klient, So'rov
  menyular.py    — Bot menyular (BotMenuRol, BotTugma) + FAQ
  tizim.py       — Harakatlar (AuditLog), Adminlar, SupervisorGroup, ...

Yangi admin qo'shish:
  1. Tegishli faylni oching (yoki yangi fayl yarating)
  2. @admin.register(Model) decorator bilan class yozing
  3. Bu faylga import qo'shing
"""

from django.contrib import admin

from .xodimlar import XodimAdmin, XabarAdmin, XabarGuruhiAdmin          # noqa: F401
from .klientlar import KlientAdmin, SorovAdmin                           # noqa: F401
from .menyular import BotMenuRolAdmin, BotTugmaAdmin, BotSlashBuyruqAdmin, FaqKategoriyaAdmin, FaqAdmin  # noqa: F401
from .tizim import (                                                     # noqa: F401
    AuditLogAdmin, AdminUserAdmin, SupervisorGroupAdmin,
    InstruksiyaAdmin, BiriktirishAdmin, CheckerFaollikAdmin,
    BaholashAdmin, AdminMsgMapAdmin,
)

admin.site.site_header  = "Dusel Company Bot — Admin"
admin.site.site_title   = "Dusel Bot Admin"
admin.site.index_title  = "Boshqaruv paneli"
