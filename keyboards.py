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


def xodim_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["❓ Ko'p So'raladigan Savollar"]],
        resize_keyboard=True,
    )


def admin_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📊 Statistika",              "👥 Xodimlar"],
            ["⏳ Kutilayotgan so'rovlar",  "🚫 Bloklanganlar"],
            ["📝 Xodimni Tahrirlash",      "📥 Excel"],
            ["🔍 Xodim Qidirish",          "🔗 Biriktirish"],
        ],
        resize_keyboard=True,
    )


def edit_select_kb(rows: list, page: int) -> InlineKeyboardMarkup:
    """Paginated employee selector for the edit flow."""
    total = len(rows)
    start = page * PAGE_SIZE
    end   = min(start + PAGE_SIZE, total)

    buttons = []
    for r in rows[start:end]:
        # rows: (ism, lavozim, filial, kod, user_id)
        buttons.append([InlineKeyboardButton(
            f"👤 {r[0]} — {r[1]} | {r[2]}",
            callback_data=f"edit_select_{r[4]}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"edit_page_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("Keyingi ▶️", callback_data=f"edit_page_{page + 1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


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


def group_sorov_inline(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Jarayonda", callback_data=f"grp_prog_{group_id}"),
        InlineKeyboardButton("✅ Bajarildi",  callback_data=f"grp_done_{group_id}"),
    ]])


def group_bajarildi_inline(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Bajarildi", callback_data=f"grp_done_{group_id}"),
    ]])


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


def faq_kategoriyalar_kb(rows: list) -> InlineKeyboardMarkup:
    """rows: [(id, emoji, nomi), ...]"""
    buttons = [[InlineKeyboardButton(f"{r[1]} {r[2]}", callback_data=f"faq_kat_{r[0]}")] for r in rows]
    return InlineKeyboardMarkup(buttons)


def faq_savollar_kb(rows: list, kategoriya_id: int) -> InlineKeyboardMarkup:
    """rows: [(id, savol), ...]"""
    buttons = [[InlineKeyboardButton(r[1], callback_data=f"faq_sav_{r[0]}")] for r in rows]
    buttons.append([InlineKeyboardButton("⬅️ Kategoriyalar", callback_data="faq_back")])
    return InlineKeyboardMarkup(buttons)


def faq_javob_kb(faq_id: int, kategoriya_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ Savollar", callback_data=f"faq_kat_{kategoriya_id}"),
        InlineKeyboardButton("🏠 Bosh menyu", callback_data="faq_back"),
    ]])


def biriktirish_agents_kb(rows: list) -> InlineKeyboardMarkup:
    """rows: [(ism, lavozim, filial, kod, user_id, status), ...]"""
    buttons = []
    for r in rows:
        cur = "🔗" if True else ""  # will be set dynamically
        buttons.append([InlineKeyboardButton(
            f"👤 {r[0]} | {r[2]}",
            callback_data=f"bir_agent_{r[4]}",
        )])
    return InlineKeyboardMarkup(buttons)


def biriktirish_checkers_kb(rows: list) -> InlineKeyboardMarkup:
    """rows: [(ism, lavozim, filial, kod, user_id, status), ...]"""
    buttons = [[InlineKeyboardButton(
        f"👤 {r[0]} — {r[1]} | {r[2]}",
        callback_data=f"bir_checker_{r[4]}",
    )] for r in rows]
    buttons.append([InlineKeyboardButton("🚫 Biriktirmaslik (o'chirish)", callback_data="bir_none")])
    return InlineKeyboardMarkup(buttons)


def checker_sorov_kb(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"bir_tasd_{group_id}"),
        InlineKeyboardButton("❌ Rad etish",  callback_data=f"bir_rad_{group_id}"),
    ]])


def search_results_kb(rows: list) -> InlineKeyboardMarkup:
    """rows: [(ism, lavozim, filial, kod, user_id, status), ...]"""
    STATUS_EMOJI = {"approved": "✅", "pending": "⏳", "blocked": "🚫"}
    buttons = []
    for r in rows:
        s = STATUS_EMOJI.get(r[5], "❓")
        buttons.append([InlineKeyboardButton(
            f"{s} {r[0]} — {r[1]} | {r[2]}",
            callback_data=f"xodim_profil_{r[4]}",
        )])
    return InlineKeyboardMarkup(buttons)


def xodim_profil_kb(user_id: int, status: str) -> InlineKeyboardMarkup:
    buttons = []
    if status == "pending":
        buttons.append([
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"appr_{user_id}"),
            InlineKeyboardButton("❌ Rad etish",  callback_data=f"reje_{user_id}"),
        ])
        buttons.append([InlineKeyboardButton("🚫 Bloklash", callback_data=f"block_{user_id}")])
    elif status == "approved":
        buttons.append([InlineKeyboardButton("🚫 Bloklash", callback_data=f"block_{user_id}")])
    elif status == "blocked":
        buttons.append([InlineKeyboardButton("🔓 Blokdan ochish", callback_data=f"unbl_{user_id}")])
    return InlineKeyboardMarkup(buttons)


def unblock_inline(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔓 Blokdan ochish", callback_data=f"unbl_{user_id}"),
    ]])
