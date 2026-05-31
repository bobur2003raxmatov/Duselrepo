"""
config.py — Django settings uchun thin wrapper.

Barcha konstantalar dusel/settings.py da saqlanadi.
Bu fayl import muvofiqligini ta'minlaydi — handlerlar o'zgarishsiz ishlaydi.
"""
from django.conf import settings

TOKEN               = settings.TELEGRAM_TOKEN
ADMIN_ID            = settings.ADMIN_ID
GROUP_CHAT_ID       = settings.GROUP_CHAT_ID
DB_PATH             = settings.DB_PATH
WEBHOOK_URL         = settings.WEBHOOK_URL
PORT                = settings.PORT

FILIALLAR           = settings.FILIALLAR
LAVOZIMLAR          = settings.LAVOZIMLAR
DOKON_TURLARI       = settings.DOKON_TURLARI
DOKON_SLUGLARI      = settings.DOKON_SLUGLARI
AGENT_PREFIX_REGIONS = settings.AGENT_PREFIX_REGIONS
AGENT_DATABASE      = settings.AGENT_DATABASE
SUPERVISOR_KODLAR   = settings.SUPERVISOR_KODLAR
BRENDLAR_LIST       = settings.BRENDLAR_LIST
VIZIT_KUNLARI       = settings.VIZIT_KUNLARI
CHASTOTA_LIST       = settings.CHASTOTA_LIST
KATEGORIYA_LIST     = settings.KATEGORIYA_LIST
KLIENT_EDIT_LABELS  = settings.KLIENT_EDIT_LABELS

SLA_TIMEOUT_SEC     = settings.SLA_TIMEOUT_SEC
GROUP_TIMEOUT_SEC   = settings.GROUP_TIMEOUT_SEC
URGENCY_TIMEOUT_SEC = settings.URGENCY_TIMEOUT_SEC
CHECKER_TIMEOUT_SEC = settings.CHECKER_TIMEOUT_SEC
BATCH_TIMEOUT_SEC   = settings.BATCH_TIMEOUT_SEC
PAGE_SIZE           = settings.PAGE_SIZE
INSTRUKSIYA_VIDEO_ID = settings.INSTRUKSIYA_VIDEO_ID

# Conversation states
ISM             = settings.ISM
LAVOZIM         = settings.LAVOZIM
KOD             = settings.KOD
FILIAL          = settings.FILIAL
TELEFON         = settings.TELEFON
TELEFON2        = settings.TELEFON2
TUGILGAN_KUN    = settings.TUGILGAN_KUN
XODIM_LIST      = settings.XODIM_LIST
EDIT_USER       = settings.EDIT_USER
EDIT_FIELD      = settings.EDIT_FIELD
EDIT_VALUE      = settings.EDIT_VALUE
SEARCH_QUERY    = settings.SEARCH_QUERY
BIRIKTIR_AGENT      = settings.BIRIKTIR_AGENT
BIRIKTIR_CHECKER    = settings.BIRIKTIR_CHECKER
BIRIKTIR_DETAIL     = settings.BIRIKTIR_DETAIL
BIRIKTIR_EDIT_FIELD = settings.BIRIKTIR_EDIT_FIELD
BIRIKTIR_EDIT_VALUE = settings.BIRIKTIR_EDIT_VALUE

KLIENT_RASM         = settings.KLIENT_RASM
KLIENT_FIRMA_NOMI   = settings.KLIENT_FIRMA_NOMI
KLIENT_TELEFON1     = settings.KLIENT_TELEFON1
KLIENT_TELEFON2     = settings.KLIENT_TELEFON2
KLIENT_INN          = settings.KLIENT_INN
KLIENT_ORIENTER     = settings.KLIENT_ORIENTER
KLIENT_LOKATSIYA    = settings.KLIENT_LOKATSIYA
KLIENT_KATEGORIYA   = settings.KLIENT_KATEGORIYA
KLIENT_DOKON_TURI   = settings.KLIENT_DOKON_TURI
KLIENT_DISTRIBUTOR  = settings.KLIENT_DISTRIBUTOR
KLIENT_AGENT_KOD    = settings.KLIENT_AGENT_KOD
KLIENT_VIZIT_KUN    = settings.KLIENT_VIZIT_KUN
KLIENT_CHASTOTA     = settings.KLIENT_CHASTOTA
KLIENT_LIMIT        = settings.KLIENT_LIMIT
KLIENT_BRENDLAR     = settings.KLIENT_BRENDLAR
KLIENT_CONFIRM      = settings.KLIENT_CONFIRM
KLIENT_EDIT_FIELD   = settings.KLIENT_EDIT_FIELD
KLIENT_EDIT_VALUE   = settings.KLIENT_EDIT_VALUE

SOROV_TUR           = settings.SOROV_TUR
SOROV_DOKON         = settings.SOROV_DOKON
SOROV_LOK           = settings.SOROV_LOK
SOROV_TEL           = settings.SOROV_TEL
SOROV_FOTO          = settings.SOROV_FOTO
SOROV_IZOH          = settings.SOROV_IZOH
SOROV_MSG           = settings.SOROV_MSG
LIMIT_DOKON         = settings.LIMIT_DOKON
LIMIT_SUMMA         = settings.LIMIT_SUMMA
SOROV_BATCH_COLLECT = settings.SOROV_BATCH_COLLECT
SOROV_BATCH_PREVIEW = settings.SOROV_BATCH_PREVIEW
SOROV_CONFIRM       = settings.SOROV_CONFIRM

INSTR_MATN   = settings.INSTR_MATN
ADD_ADMIN_ID = settings.ADD_ADMIN_ID
