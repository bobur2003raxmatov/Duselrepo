import re

from telegram import (
    ReplyKeyboardMarkup, ReplyKeyboardRemove,
    KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton,
)
from config import FILIALLAR, LAVOZIMLAR, PAGE_SIZE


def _dokon_slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


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
        [["⏭ O'tkazib yuborish"]],
        resize_keyboard=True, one_time_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()



def excel_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Xodimlar hisoboti",      callback_data="excel_xodimlar")],
        [InlineKeyboardButton("🏪 Ochilgan klientlar Excel", callback_data="excel_klientlar")],
    ])


def klientlar_stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Klient qidirish", callback_data="klient_search_start")],
    ])


def agent_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["❓ So'rov"]],
        resize_keyboard=True,
    )


def supervisor_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["🏪 Yangi Klient", "📝 Muammo yozish"]],
        resize_keyboard=True,
    )


def filial_rahbari_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["🏪 Dokon qo'shish"],
            ["💰 Limit qo'shish", "📝 Muammo yozish"],
        ],
        resize_keyboard=True,
    )


def batch_collect_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["📤 Yuborish"]], resize_keyboard=True)


def batch_preview_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tasdiqlash va yuborish",    callback_data="batch_confirm")],
        [InlineKeyboardButton("✏️ Tahrirlash (yana qo'shish)", callback_data="batch_edit")],
        [InlineKeyboardButton("❌ Bekor qilish",               callback_data="batch_cancel")],
    ])


def sorov_tur_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📍 Dokon lokatsiyasini o'zgartirish", callback_data="sorov_tur_lokatsiya")],
        [InlineKeyboardButton("📞 Dokon raqamini o'zgartirish",      callback_data="sorov_tur_telefon")],
        [InlineKeyboardButton("🖼 Vizitda muammo",                    callback_data="sorov_tur_vizit")],
        [InlineKeyboardButton("💬 Boshqa muammo",                    callback_data="sorov_tur_boshqa")],
    ])


def sorov_tasdiqlash_kb(sorov_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"sorov_appr_{sorov_id}"),
        InlineKeyboardButton("❌ Rad etish",  callback_data=f"sorov_rej_{sorov_id}"),
    ]])


def admin_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📊 Statistika",              "👥 Xodimlar"],
            ["⏳ Kutilayotgan so'rovlar",  "🚫 Bloklanganlar"],
            ["📥 Excel",                   "🔗 Biriktirish"],
            ["🏪 Yangi Klient",            "🏪 Klientlar"],
            ["🏆 Reyting",                 "📋 Tarix"],
        ],
        resize_keyboard=True,
    )


def tarix_filter_kb(active: str = "all") -> InlineKeyboardMarkup:
    def _btn(label: str, ft: str) -> InlineKeyboardButton:
        mark = "• " if ft == active else ""
        return InlineKeyboardButton(f"{mark}{label}", callback_data=f"tarix_f_{ft}")
    return InlineKeyboardMarkup([[
        _btn("Barchasi",      "all"),
        _btn("Agentlar",      "agent"),
        _btn("Supervisorlar", "supervisor"),
        _btn("Rad etilganlar","rejected"),
    ]])


def reyting_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏆 Agent reytingi", callback_data="reyting_agent"),
            InlineKeyboardButton("🏢 Filial reytingi", callback_data="reyting_filial"),
        ],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="reyting_close")],
    ])


def agent_reyting_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Orqaga", callback_data="reyting_menu"),
    ]])


def edit_field_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["Ism", "Lavozim"], ["Kod", "Filial"], ["❌ Bekor qilish"]],
        resize_keyboard=True, one_time_keyboard=True,
    )


def xodimlar_page_inline(rows: list, page: int) -> InlineKeyboardMarkup:
    total = len(rows)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)

    buttons = []
    for r in rows[start:end]:
        buttons.append([InlineKeyboardButton(
            f"👤 {r[0]} — {r[1]} | {r[2]}",
            callback_data=f"xodim_profil_{r[4]}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"xod_page_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("Keyingi ▶️", callback_data=f"xod_page_{page + 1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


def xodimlar_edit_page_inline(rows: list, page: int) -> InlineKeyboardMarkup:
    """Unified employee menu with edit buttons."""
    total = len(rows)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)

    buttons = []
    for r in rows[start:end]:
        buttons.append([
            InlineKeyboardButton(f"👤 {r[0]} — {r[1]} | {r[2]}", callback_data=f"xodim_info_{r[4]}"),
            InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"xodim_edit_{r[4]}"),
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"xodim_list_page_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("Keyingi ▶️", callback_data=f"xodim_list_page_{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("🔍 Qidirish", callback_data="xodim_search_start")])
    return InlineKeyboardMarkup(buttons)


def group_sorov_inline(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Jarayonda", callback_data=f"grp_prog_{group_id}"),
            InlineKeyboardButton("✅ Bajarildi",  callback_data=f"grp_done_{group_id}"),
        ],
        [InlineKeyboardButton("📋 Tafsilotlar", callback_data=f"grp_detail_{group_id}")],
    ])


def group_bajarildi_inline(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Bajarildi", callback_data=f"grp_done_{group_id}")],
        [InlineKeyboardButton("📋 Tafsilotlar", callback_data=f"grp_detail_{group_id}")],
    ])


def group_detail_back_inline(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ Orqaga", callback_data=f"grp_back_{group_id}"),
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


def biriktirish_list_kb(assigned: list, unassigned: list) -> InlineKeyboardMarkup:
    """assigned: [(agent_id,agent_ism,checker_id,checker_ism,filial,status)]
       unassigned: [(ism,user_id,filial,kod)]"""
    buttons = []
    for a in assigned:
        status_icon = "✅" if a[5] == "approved" else "🚫"
        buttons.append([InlineKeyboardButton(
            f"{status_icon} {a[1]} → {a[3] or '?'} | {a[4]}",
            callback_data=f"bir_detail_{a[0]}",
        )])
    for u in unassigned:
        buttons.append([InlineKeyboardButton(
            f"❗ {u[0]} | {u[2]} (checker yo'q)",
            callback_data=f"bir_detail_{u[1]}",
        )])
    buttons.append([InlineKeyboardButton("➕ Yangi biriktirish", callback_data="bir_new")])
    return InlineKeyboardMarkup(buttons)


def biriktir_detail_kb(agent_id: int, status: str, has_checker: bool) -> InlineKeyboardMarkup:
    uid = agent_id
    buttons = [
        [
            InlineKeyboardButton("📝 Ism",     callback_data=f"bir_ef_ism_{uid}"),
            InlineKeyboardButton("💼 Lavozim", callback_data=f"bir_ef_lavozim_{uid}"),
        ],
        [
            InlineKeyboardButton("🔑 Kod",    callback_data=f"bir_ef_kod_{uid}"),
            InlineKeyboardButton("🏢 Filial", callback_data=f"bir_ef_filial_{uid}"),
        ],
    ]
    if has_checker:
        buttons.append([
            InlineKeyboardButton("🔄 Checker almashtirish", callback_data=f"bir_change_{uid}"),
            InlineKeyboardButton("🗑 O'chirish",             callback_data=f"bir_rm_{uid}"),
        ])
    else:
        buttons.append([InlineKeyboardButton("➕ Checker biriktirish", callback_data=f"bir_change_{uid}")])

    if status == "approved":
        buttons.append([InlineKeyboardButton("🚫 Bloklash", callback_data=f"bir_block_{uid}")])
    elif status == "blocked":
        buttons.append([InlineKeyboardButton("🔓 Blokdan ochish", callback_data=f"bir_unblock_{uid}")])

    buttons.append([InlineKeyboardButton("⬅️ Ro'yxatga qaytish", callback_data="bir_back")])
    return InlineKeyboardMarkup(buttons)


def biriktirish_agents_kb(rows: list) -> InlineKeyboardMarkup:
    """Yangi biriktirish uchun agent tanlash (biriktirilmaganlar)."""
    buttons = [[InlineKeyboardButton(
        f"👤 {r[0]} | {r[2]}",
        callback_data=f"bir_agent_{r[1]}",
    )] for r in rows]
    buttons.append([InlineKeyboardButton("⬅️ Ortga", callback_data="bir_back")])
    return InlineKeyboardMarkup(buttons)


def biriktirish_checkers_kb(rows: list) -> InlineKeyboardMarkup:
    """rows: [(ism, lavozim, filial, kod, user_id, status), ...]"""
    buttons = [[InlineKeyboardButton(
        f"👤 {r[0]} — {r[1]} | {r[2]}",
        callback_data=f"bir_checker_{r[4]}",
    )] for r in rows]
    buttons.append([InlineKeyboardButton("🚫 Biriktirmaslik (o'chirish)", callback_data="bir_none")])
    return InlineKeyboardMarkup(buttons)


def urgency_kb(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔴 Shoshilinch", callback_data=f"urgency_{group_id}_shoshilinch"),
        InlineKeyboardButton("🟡 O'rta",       callback_data=f"urgency_{group_id}_orta"),
        InlineKeyboardButton("🟢 Oddiy",       callback_data=f"urgency_{group_id}_oddiy"),
    ]])


def stars_kb(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⭐",      callback_data=f"star_{group_id}_1"),
        InlineKeyboardButton("⭐⭐",    callback_data=f"star_{group_id}_2"),
        InlineKeyboardButton("⭐⭐⭐",  callback_data=f"star_{group_id}_3"),
        InlineKeyboardButton("⭐⭐⭐⭐", callback_data=f"star_{group_id}_4"),
        InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data=f"star_{group_id}_5"),
    ]])


def filial_filter_kb(active: str = "haftalik") -> InlineKeyboardMarkup:
    def btn(label: str, key: str) -> InlineKeyboardButton:
        text = f"▶ {label}" if key == active else label
        return InlineKeyboardButton(text, callback_data=f"filial_lider_{key}")
    return InlineKeyboardMarkup([
        [
            btn("Haftalik", "haftalik"),
            btn("Oylik",    "oylik"),
            btn("Yillik",   "yillik"),
            btn("Hammasi",  "hammasi"),
        ],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="reyting_menu")],
    ])


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


def xodim_profil_kb(user_id: int, status: str, lavozim: str = "") -> InlineKeyboardMarkup:
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
    if lavozim in ("Supervisor", "Filial Rahbari"):
        buttons.append([InlineKeyboardButton("🔗 Guruh belgilash", callback_data=f"xodim_setgroup_{user_id}")])
    return InlineKeyboardMarkup(buttons)


def limit_appr_rej_kb(sorov_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"limit_appr_{sorov_id}"),
        InlineKeyboardButton("❌ Rad etish",  callback_data=f"limit_rej_{sorov_id}"),
    ]])


def pending_xodimlar_inline(rows: list, page: int) -> InlineKeyboardMarkup:
    total = len(rows)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)

    buttons = []
    for r in rows[start:end]:
        buttons.append([InlineKeyboardButton(
            f"⏳ {r[1]} ({r[2]}) | {r[4]}",
            callback_data=f"xodim_profil_{r[0]}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"pending_page_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("Keyingi ▶️", callback_data=f"pending_page_{page + 1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


def blocked_xodimlar_inline(rows: list, page: int) -> InlineKeyboardMarkup:
    total = len(rows)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)

    buttons = []
    for r in rows[start:end]:
        buttons.append([InlineKeyboardButton(
            f"🚫 {r[1]} | Kod: {r[4]}",
            callback_data=f"xodim_profil_{r[0]}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"blocked_page_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("Keyingi ▶️", callback_data=f"blocked_page_{page + 1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


def unblock_inline(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔓 Blokdan ochish", callback_data=f"unbl_{user_id}"),
    ]])


# ═══════════════════════════════════════════════════════════════════════════════════
# KLIENT REGISTRATSIYA KLAVIATURALARI
# ═══════════════════════════════════════════════════════════════════════════════════

def klient_lokatsiya_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📍 GPS joylashuv ulashish", callback_data="lok_gps")],
        [InlineKeyboardButton("✏️ Manzilni qo'lda kiritish", callback_data="lok_text")],
    ])


def klient_dokon_turi_kb() -> InlineKeyboardMarkup:
    from config import DOKON_TURLARI
    buttons = [[InlineKeyboardButton(tur, callback_data=f"klient_tur_{_dokon_slug(tur)}")] for tur in DOKON_TURLARI]
    return InlineKeyboardMarkup(buttons)


def klient_vizit_kun_kb() -> InlineKeyboardMarkup:
    from config import VIZIT_KUNLARI
    buttons = [[InlineKeyboardButton(kun, callback_data=f"klient_kun_{i}")] for i, kun in enumerate(VIZIT_KUNLARI)]
    return InlineKeyboardMarkup(buttons)


def klient_chastota_kb() -> InlineKeyboardMarkup:
    from config import CHASTOTA_LIST
    buttons = [[InlineKeyboardButton(ch, callback_data=f"klient_chas_{i}")] for i, ch in enumerate(CHASTOTA_LIST)]
    return InlineKeyboardMarkup(buttons)


def klient_distributor_kb(distributors: list) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(f"{d[0]} ({d[2]})", callback_data=f"klient_dist_{d[4]}")] for d in distributors]
    buttons.append([InlineKeyboardButton("⬅️ Ortga", callback_data="klient_cancel")])
    return InlineKeyboardMarkup(buttons)


def klient_agent_kb(agents: list) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(f"{a[0]} ({a[3]})", callback_data=f"klient_agent_{a[4]}")] for a in agents]
    buttons.append([InlineKeyboardButton("⬅️ Ortga", callback_data="klient_cancel")])
    return InlineKeyboardMarkup(buttons)


def klient_brendlar_kb() -> InlineKeyboardMarkup:
    from config import BRENDLAR_LIST
    buttons = [[InlineKeyboardButton(f"☐ {b}", callback_data=f"klient_brand_{i}")] for i, b in enumerate(BRENDLAR_LIST)]
    buttons.append([InlineKeyboardButton("✅ Tasdiqla", callback_data="klient_brands_confirm")])
    buttons.append([InlineKeyboardButton("⬅️ Ortga", callback_data="klient_cancel")])
    return InlineKeyboardMarkup(buttons)


def klient_brendlar_kb_selected(selected: list) -> InlineKeyboardMarkup:
    from config import BRENDLAR_LIST
    buttons = []
    for i, b in enumerate(BRENDLAR_LIST):
        icon = "☑️" if i in selected else "☐"
        buttons.append([InlineKeyboardButton(f"{icon} {b}", callback_data=f"klient_brand_{i}")])
    buttons.append([InlineKeyboardButton("✅ Tasdiqla", callback_data="klient_brands_confirm")])
    buttons.append([InlineKeyboardButton("⬅️ Ortga", callback_data="klient_cancel")])
    return InlineKeyboardMarkup(buttons)


def klient_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tasdiqlash", callback_data="klient_submit")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="klient_cancel")],
    ])


def klientlar_page_inline(rows: list, page: int) -> InlineKeyboardMarkup:
    total = len(rows)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)

    buttons = []
    for r in rows[start:end]:
        status_icon = "✅" if r[17] == "approved" else "⏳" if r[17] == "pending" else "❌"
        buttons.append([InlineKeyboardButton(
            f"{status_icon} {r[2]} | {r[11]} | INN: {r[5]}",
            callback_data=f"klient_view_{r[0]}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"klientlar_page_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("Keyingi ▶️", callback_data=f"klientlar_page_{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("🔍 Klient qidirish", callback_data="klient_search_start")])
    return InlineKeyboardMarkup(buttons)


def klientlar_search_page_inline(rows: list, page: int) -> InlineKeyboardMarkup:
    total = len(rows)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)

    buttons = []
    for r in rows[start:end]:
        status_icon = "✅" if r[17] == "approved" else "⏳" if r[17] == "pending" else "❌"
        buttons.append([InlineKeyboardButton(
            f"{status_icon} {r[2]} | {r[11]} | INN: {r[5]}",
            callback_data=f"klient_view_{r[0]}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"klientlar_search_page_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("Keyingi ▶️", callback_data=f"klientlar_search_page_{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("🔍 Yangi qidirish", callback_data="klient_search_start")])
    return InlineKeyboardMarkup(buttons)


def klient_approval_kb(klient_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"klient_approve_{klient_id}")],
        [InlineKeyboardButton("❌ Rad etish", callback_data=f"klient_reject_{klient_id}")],
    ])


def mening_klientlar_kb(rows: list, page: int, page_size: int = 5) -> InlineKeyboardMarkup:
    total = len(rows)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = page * page_size
    end = min(start + page_size, total)

    buttons = []
    for r in rows[start:end]:
        status_icon = "✅" if r[17] == "approved" else "⏳" if r[17] == "pending" else "❌"
        buttons.append([InlineKeyboardButton(
            f"{status_icon} {r[2]} | {r[3]}",
            callback_data=f"mk_view_{r[0]}_{page}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"mk_page_{page - 1}"))
    nav.append(InlineKeyboardButton(f"Sahifa {page + 1}/{total_pages}", callback_data="mk_noop"))
    if end < total:
        nav.append(InlineKeyboardButton("Keyingi ▶️", callback_data=f"mk_page_{page + 1}"))
    buttons.append(nav)

    return InlineKeyboardMarkup(buttons)
