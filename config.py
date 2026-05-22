import os

TOKEN         = os.environ.get("TOKEN", "8465121120:AAH8Gz0qKC-S0RCe7n8PswzCMMu-Igd4qx8")
ADMIN_ID      = int(os.environ.get("ADMIN_ID", "7839267271"))
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

URGENCY_TIMEOUT_SEC = 60   # urgency tanlanmasa shu soniyadan keyin oddiy deb hisoblanadi
CHECKER_TIMEOUT_SEC = 1800 # checker 30 daqiqada javob bermasa admin ogohlantiriladi

# Pagination
PAGE_SIZE = 10
