import os

TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("❌ TOKEN environment variable is required. Set it before running the bot.")

ADMIN_ID = int(os.environ.get("ADMIN_ID", "7839267271"))
GROUP_CHAT_ID = -1003802115020
DB_PATH       = os.environ.get("DB_PATH", "dusel_company.db")

FILIALLAR = [
    "Namangan Tools", "Navoiy Tools", "Qashqadaryo Tools", "Samarqand Tools",
    "Test Filial",    "Xorazasp",     "Andijon",            "Buxoro",
    "Gijduvon",       "Denov",        "Jizzax",             "Qo'qon",
    "Qoson",          "Nukus",        "Samarqand",          "Termiz",
    "Toshkent",       "Farg'ona",     "Xorazm",
]

LAVOZIMLAR = ["Filial Rahbari", "Supervisor", "Agent", "Operator", "Distribyutor"]

DOKON_TURLARI = ["Bozor", "Supermarket", "Mini market", "Magazin", "Apteka", "Ombor", "Boshqa"]
BRENDLAR_LIST = ["Dusel", "Verla", "Cable", "Ockean", "Tools"]
VIZIT_KUNLARI = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"]
CHASTOTA_LIST = ["1x1 (har hafta)", "2x1 (ikki haftada)", "1x1 (oyda)"]

SLA_TIMEOUT_SEC   = 900  # 15 daqiqa
GROUP_TIMEOUT_SEC = 60   # 1 daqiqa — bir guruhga birlashish oynasi

# Conversation states
ISM, LAVOZIM, KOD, FILIAL, TELEFON, TELEFON2, TUGILGAN_KUN = range(7)
EDIT_USER, EDIT_FIELD, EDIT_VALUE = range(7, 10)
SEARCH_QUERY        = 10
BIRIKTIR_AGENT      = 11
BIRIKTIR_CHECKER    = 12
BIRIKTIR_DETAIL     = 13
BIRIKTIR_EDIT_FIELD = 14
BIRIKTIR_EDIT_VALUE = 15

# Client registration states (16 steps)
KLIENT_RASM         = 20
KLIENT_FIRMA_NOMI   = 21
KLIENT_TELEFON1     = 22
KLIENT_TELEFON2     = 23
KLIENT_INN          = 24
KLIENT_ORIENTER     = 25
KLIENT_LOKATSIYA    = 26
KLIENT_KATEGORIYA   = 27
KLIENT_DOKON_TURI   = 28
KLIENT_DISTRIBUTOR  = 29
KLIENT_AGENT_KOD    = 30
KLIENT_VIZIT_KUN    = 31
KLIENT_CHASTOTA     = 32
KLIENT_LIMIT        = 33
KLIENT_BRENDLAR     = 34
KLIENT_CONFIRM      = 35

URGENCY_TIMEOUT_SEC = 60   # urgency tanlanmasa shu soniyadan keyin oddiy deb hisoblanadi
CHECKER_TIMEOUT_SEC = 1800 # checker 30 daqiqada javob bermasa admin ogohlantiriladi

# Pagination
PAGE_SIZE = 10
