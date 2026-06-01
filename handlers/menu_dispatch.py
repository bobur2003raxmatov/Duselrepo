"""
menu_dispatch.py — DB dan olingan menyu tugmalarini bot handler larga ulaydi.

Avtomatik yangilanish:
  - Bot har 30 soniyada DB dan menyularni qayta yuklaydi.
  - Telegram slash buyruqlari ham shu vaqtda yangilanadi.
  - Django admin da o'zgarish → 30 soniya ichida botga yetadi.
"""
import logging
from telegram.ext import filters

logger = logging.getLogger(__name__)

# ── Kesh ─────────────────────────────────────────────────────────────────────
_BUYRUQ_TEXTS: dict[str, set[str]] = {}   # buyruq  → {matn, ...}
_KB_ROWS:      dict[str, list]     = {}   # lavozim → [[matn, ...], ...]
_MATN_EXTRA:   dict[str, str]      = {}   # matn    → extra (matn_javob uchun)


def refresh_menu_cache(tugmalar: list) -> None:
    """DB dan olingan BotTugma ro'yxati bilan keshni yangilaydi."""
    _BUYRUQ_TEXTS.clear()
    _KB_ROWS.clear()
    _MATN_EXTRA.clear()

    kb_raw: dict[str, dict[int, list]] = {}

    for t in tugmalar:
        lavozim = t.rol.lavozim
        _BUYRUQ_TEXTS.setdefault(t.buyruq, set()).add(t.matn)
        kb_raw.setdefault(lavozim, {}).setdefault(t.qator, []).append((t.ustun, t.matn))
        if t.buyruq == "matn_javob" and t.extra:
            _MATN_EXTRA[t.matn] = t.extra

    for lavozim, rows_dict in kb_raw.items():
        _KB_ROWS[lavozim] = [
            [matn for _, matn in sorted(cells)]
            for _, cells in sorted(rows_dict.items())
        ]

    logger.info(
        f"[MenuCache] yangilandi: {len(_KB_ROWS)} lavozim, "
        f"{sum(len(v) for v in _BUYRUQ_TEXTS.values())} tugma"
    )


def get_kb_rows(lavozim: str) -> list[list[str]] | None:
    return _KB_ROWS.get(lavozim)


def get_matn_extra(matn: str) -> str | None:
    return _MATN_EXTRA.get(matn)


class BuyruqFilter(filters.MessageFilter):
    """
    Telegram filter — buyruq ga mos BARCHA tugma matnlarini ushlaydi.
    defaults — hardcoded zaxira matnlar (DB o'chib qolsa ham ishlaydi).
    """
    def __init__(self, buyruq: str, defaults: tuple[str, ...] = ()):
        self.buyruq    = buyruq
        self._defaults = frozenset(defaults)
        super().__init__()

    def filter(self, message) -> bool:
        txt = message.text
        if not txt:
            return False
        return txt in self._defaults or txt in _BUYRUQ_TEXTS.get(self.buyruq, set())
