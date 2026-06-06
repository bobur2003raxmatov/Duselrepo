import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dusel-bot-please-change-in-production-xyz123",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "bot_app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "dusel.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "dusel.wsgi.application"
ASGI_APPLICATION = "dusel.asgi.application"

# ── Database ──────────────────────────────────────────────────────
_db_path = os.environ.get("DB_PATH", "dusel_company.db")
_db_file = Path(_db_path) if Path(_db_path).is_absolute() else BASE_DIR / _db_path

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": _db_file,
        "OPTIONS": {
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
    }
}

# ── Internationalisation ──────────────────────────────────────────
LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = False

# ── Static ────────────────────────────────────────────────────────
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Logging ───────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "main": {
            "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "formatter": "main",
        },
    },
    "root": {
        "handlers": ["stderr"],
        "level": "WARNING",
    },
    "loggers": {
        "bot_app": {
            "handlers": ["stderr"],
            "level": "INFO",
            "propagate": False,
        },
        "telegram": {
            "handlers": ["stderr"],
            "level": "INFO",
            "propagate": False,
        },
        "httpx": {
            "handlers": ["stderr"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["stderr"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# ══════════════════════════════════════════════════════════════════
# Telegram Bot sozlamalari
# ══════════════════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.environ.get("TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7839267271"))
GROUP_CHAT_ID = -1003802115020
DB_PATH = _db_path
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").rstrip("/")
PORT = int(os.environ.get("PORT", "8443"))

# ── Filiallar va lavozimlar ───────────────────────────────────────
FILIALLAR = [
    "Namangan Tools", "Navoiy Tools", "Qashqadaryo Tools", "Samarqand Tools",
    "Test Filial",    "Xorazasp",     "Andijon",            "Buxoro",
    "Gijduvon",       "Denov",        "Jizzax",             "Qo'qon",
    "Qoson",          "Nukus",        "Samarqand",          "Termiz",
    "Toshkent",       "Farg'ona",     "Xorazm",
]

LAVOZIMLAR = ["Filial Rahbari", "Supervisor", "Agent", "Operator", "Distribyutor"]

DOKON_TURLARI = [
    "Elektromarket",
    "Elektrotexnika",
    "Elektrotovar",
    "Elektrotovar Lyustra",
    "Gipermarket",
    "Kabel, Avtomatika",
    "Lyustra",
    "Oziq-ovqat",
    "Quruvchi",
    "Santexnika",
    "Xoz Mag",
    "Boshqa",
]
DOKON_SLUGLARI = {re.sub(r"[^a-z0-9]+", "_", k.lower()).strip("_"): k for k in DOKON_TURLARI}

AGENT_PREFIX_REGIONS = {
    "AN": "Andijon",
    "BX": "Buxoro",
    "FA": "Farg'ona",
    "QQ": "Qoraqalpog'iston",
    "TM": "Toshkent",
    "XM": "Xorazm",
    "JZ": "Jizzax",
    "KS": "Qashqadaryo",
    "SM": "Samarqand",
    "NM": "Namangan",
    "NK": "Namangan",
    "NV": "Navoiy",
    "GJ": "Qashqadaryo",
}

AGENT_DATABASE = {
    "AN01": "Abdusattorov Fazliddin",
    "AN02": "Xojibaxromov Xalilulloh",
    "AN04": "Topvoldiyev Mirzohid",
    "AN05": "Raxmatullayev Ilhomjon",
    "AN07": "Nematov Azizbek",
    "AN08": "Hakimov Mavlonbek",
    "BX01": "Vokhidov Abdumalik",
    "BX02": "Zubaydullayev Jamhur",
    "BX03": "Nematov Ahmed",
    "BX04": "Amodillayev Mirshod",
    "FA01": "Marufiov Ro'zimuhammad",
    "FA02": "Toshpo'latov Muhammadjon",
    "FA03": "Mirzaliyev Abdulatif",
    "FA07": "Erkinjonov Shoxrux",
    "QQ01": "Mahkamov Muzaffar",
    "QQ02": "Muhammadjonov Rashidjon",
    "QQ03": "Azimov Abrorxon",
    "QQ08": "Fayzullaxojayev Obidxoja",
    "TM02": "Mo'minov Shaxzod",
    "TM03": "Orzuqulov Abdunazar",
    "TM04": "Rustamov Umidjon",
    "TM05": "Xayitov Umid",
    "TM07": "To'raboyev Umidjon",
    "TM08": "Kamolov Quvonchbek",
    "XM01": "Rozimov Alisher",
    "XM03": "Jumanazarov Muzaffar",
    "XM04": "Xusainov Bekzod",
    "SM01": "Jurayev Shaxboz",
    "SM02": "Bekpo'latov Qutbiddin",
    "SM03": "Xakimov Dilmurod",
    "SM04": "Abduraxmonov Elmurod",
    "SM06": "Norbo'tayev Jo'rabek",
    "SM07": "Asatullayev Inomjon",
    "GJ01": "Maqsudov Mirshod",
    "GJ02": "Sharapov Shahboz",
    "GJ03": "Muhammedov Muhammad",
    "GJ04": "Baxshillayev Behruz",
    "GJ07": "Oripov Damir",
    "NK01": "Soatboyev Suhrob",
    "NK02": "Ko'klanov Og'abek",
    "NV01": "Umrzoqov Rashid",
    "NV02": "Mamayusupov Normurod",
    "NV03": "Akramov Alisher",
    "NV05": "Axtamov Murodbek",
    "JZ01": "Muhammadiev Shaxboz",
    "JZ03": "Toshpulatov Abdunazar",
    "JZ04": "Yusupov Muhammad",
    "JZ07": "Islomov Ilhom",
    "JZ08": "Sattarov Abdusamad",
    "KS01": "Rustamov Sardor",
    "KS02": "Rustamov Azizbek",
    "KS03": "Rustamov Shaxzod",
    "KS06": "Qudratov Alimardon",
    "KS07": "Toyirov Mirjalol",
    "KS08": "Shoyimqulov Yodgor",
    "NM01": "Xakimjanov Akbar",
    "NM02": "Akbarov Akbarjon",
}

SUPERVISOR_KODLAR = {prefix + "100" for prefix in AGENT_PREFIX_REGIONS}

BRENDLAR_LIST   = ["Dusel", "Verla", "Cable", "Ockean", "Tools"]
VIZIT_KUNLARI   = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"]
CHASTOTA_LIST   = ["1x1 (har hafta)", "2x1 (ikki haftada)", "1x1 (oyda)"]
KATEGORIYA_LIST = ["A", "B", "C", "D"]

KLIENT_EDIT_LABELS = {
    "firma_nomi":  "🏢 Firma nomi",
    "telefon1":    "📱 Telefon 1",
    "telefon2":    "📱 Telefon 2",
    "inn":         "🔢 INN",
    "orienter":    "📍 Orienter",
    "kategoriya":  "🗂 Kategoriya",
    "dokon_turi":  "🏪 Do'kon turi",
    "distributor": "👤 Distributor",
    "agent_vizit": "👨 Agent kodi/Vizit",
    "chastota":    "🔄 Chastota",
    "limit_text":  "💰 Limit",
}

# ── Timeout sozlamalari ───────────────────────────────────────────
SLA_TIMEOUT_SEC     = 900   # 15 daqiqa
GROUP_TIMEOUT_SEC   = 60    # 1 daqiqa — bir guruhga birlashish oynasi
URGENCY_TIMEOUT_SEC = 60    # urgency tanlanmasa shu soniyadan keyin oddiy
CHECKER_TIMEOUT_SEC = 1800  # checker 30 daqiqada javob bermasa admin ogohlantiriladi
BATCH_TIMEOUT_SEC   = 180   # 3 daqiqa faolsiz → auto-submit

PAGE_SIZE = 10

INSTRUKSIYA_VIDEO_ID = ""

# ── Conversation states ───────────────────────────────────────────
ISM, LAVOZIM, KOD, FILIAL, TELEFON, TELEFON2, TUGILGAN_KUN = range(7)
XODIM_LIST          = 7
EDIT_USER, EDIT_FIELD, EDIT_VALUE = range(8, 11)
SEARCH_QUERY        = 11
BIRIKTIR_AGENT      = 12
BIRIKTIR_CHECKER    = 13
BIRIKTIR_DETAIL     = 14
BIRIKTIR_EDIT_FIELD = 15
BIRIKTIR_EDIT_VALUE = 16

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
KLIENT_EDIT_FIELD   = 36
KLIENT_EDIT_VALUE   = 37

SOROV_TUR           = 40
SOROV_DOKON         = 41
SOROV_LOK           = 42
SOROV_TEL           = 43
SOROV_FOTO          = 44
SOROV_IZOH          = 45
SOROV_MSG           = 46
LIMIT_DOKON         = 47
LIMIT_SUMMA         = 48
SOROV_BATCH_COLLECT = 49
SOROV_BATCH_PREVIEW = 50
SOROV_CONFIRM       = 51

INSTR_MATN   = 60
ADD_ADMIN_ID = 61
