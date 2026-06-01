"""Umumiy konstantalar — barcha admin fayllari shu yerdan import qiladi."""

ACTION_LABELS = {
    "vizit_muammo":          "📍 Vizitda muammo",
    "boshqa_muammo":         "📝 Boshqa muammo",
    "lokatsiya_ozgartirish": "📌 Lokatsiya o'zgartirish",
    "raqam_ozgartirish":     "📞 Raqam o'zgartirish",
    "supervisor_tasdiqlash": "✅ Supervisor tasdiqlash",
    "supervisor_rad":        "❌ Supervisor rad etish",
    "limit_qoshish":         "💰 Limit qo'shish",
    "dokon_qoshish":         "🏪 Do'kon qo'shish",
    "topic_deleted":         "🗑 Topic o'chirildi",
    "vizit":                 "📍 Vizit",
}

KATEGORIYA_MAP = {
    "So'rovlar":  {"vizit_muammo", "boshqa_muammo", "lokatsiya_ozgartirish", "raqam_ozgartirish", "vizit"},
    "Supervisor": {"supervisor_tasdiqlash", "supervisor_rad"},
    "Klientlar":  {"dokon_qoshish"},
    "Limit":      {"limit_qoshish"},
    "Xodimlar":   {"topic_deleted"},
}

ACTION_TO_KAT = {a: k for k, actions in KATEGORIYA_MAP.items() for a in actions}

ROLE_LABELS = {
    "agent":          "👤 Agent",
    "supervisor":     "👔 Supervisor",
    "filial_rahbari": "🏢 Filial Rahbari",
    "operator":       "🖥 Operator",
    "distribyutor":   "🚚 Distribyutor",
}

STATUS_COLORS = {
    "success": "#28a745",
    "failed":  "#dc3545",
    "pending": "#fd7e14",
}
