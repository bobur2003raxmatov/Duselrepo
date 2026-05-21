from telegram import (
    ReplyKeyboardMarkup, ReplyKeyboardRemove,
    KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton,
)
from config import FILIALLAR, LAVOZIMLAR, PAGE_SIZE


def lavozim_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[lav] for lav in LAVOZIMLAR],
        resize_keyboard=True, one_time_keyboard=True,
    )


def filial_kb() -> ReplyKeyboardMarkup:
    rows, row = [], []
    for f in FILIALLAR:
        row.append(f)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def telefon_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Raqamni ulashish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )


def telefon2_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📱 2-raqamni ulashish", request_contact=True)],
            ["⏭ O'tkazib yuborish"],
        ],
        resize_keyboard=True, one_time_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def admin_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📊 Statistika",              "👥 Xodimlar"],
            ["⏳ Kutilayotgan so'rovlar",  "🚫 Bloklanganlar"],
            ["📝 Xodimni Tahrirlash",      "📥 Excel Eksport"],
            ["🔍 Xodim Qidirish"],
        ],
        resize_keyboard=True,
    )


def edit_field_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["Ism", "Lavozim"], ["Kod", "Filial"], ["❌ Bekor qilish"]],
        resize_keyboard=True, one_time_keyboard=True,
    )


def xodimlar_page_inline(page: int, total: int) -> InlineKeyboardMarkup | None:
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"xod_page_{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        buttons.append(InlineKeyboardButton("Keyingi ▶️", callback_data=f"xod_page_{page + 1}"))
    if not buttons:
        return None
    return InlineKeyboardMarkup([buttons])


def sorov_inline(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Jarayonda", callback_data=f"prog_{task_id}"),
        InlineKeyboardButton("✅ Bajarildi",  callback_data=f"done_{task_id}"),
    ]])


def bajarildi_inline(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Bajarildi", callback_data=f"done_{task_id}"),
    ]])


def tasdiq_inline(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"appr_{user_id}"),
            InlineKeyboardButton("❌ Rad etish",  callback_data=f"reje_{user_id}"),
        ],
        [InlineKeyboardButton("🚫 Bloklash", callback_data=f"block_{user_id}")],
    ])


def unblock_inline(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔓 Blokdan ochish", callback_data=f"unbl_{user_id}"),
    ]])
