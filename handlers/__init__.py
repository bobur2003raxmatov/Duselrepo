"""
handlers/ paketi — Dusel Company bot handler'lari.

Tuzilish:
  _shared.py      — Umumiy yordamchilar: em, rate_limited, admin_only, ...
  register.py     — /start va ro'yxatdan o'tish oqimi
  chat.py         — Xodim xabarlari, reaksiyalar, topic yopilish
  admin_cmd.py    — Admin panel: statistika, xodimlar, tarix
  biriktirish.py  — Agent↔Checker biriktirish
  instruksiya.py  — Instruksiya handlerlari
  klient.py       — Klient ro'yxatdan o'tkazish va admin klientlar
  callbacks.py    — Callback router va sub-handler'lar

_core.py backwards compat uchun saqlanadi — barcha nomlarni re-export qiladi.
"""

from handlers._shared import (
    rate_limited, em, format_phone, safe_callback_int,
    admin_only, _role_keyboard,
    _format_profil,
)

from handlers.register import (
    cancel, start,
    ism_olish, lavozim_olish, kod_olish,
    filial_olish, telefon_olish, telefon2_olish,
    tugilgan_kun_olish,
)

from handlers.chat import (
    xodim_chat_handler, reaction_handler, admin_guruh_javob,
    topic_closed_handler,
)

from handlers.admin_cmd import (
    admin_statistika, admin_xodimlar,
    _xodim_list_page_cb, _xodim_info_cb, _xodim_edit_cb, _xodim_search_start_cb,
    admin_kutilayotganlar, admin_bloklanganlar, admin_excel_eksport,
    edit_field, edit_value, search_query_handler,
    admin_tarix, tarix_filter_callback,
    add_admin_command, add_admin_id_receive, admin_mgmt_callback,
    admin_upload_db,
)

from handlers.instruksiya import (
    instruksiya_cmd,
    admin_instruksiya_lavozim_cb,
    admin_instruksiya_edit_cb,
    admin_instruksiya_del_cb,
    admin_instruksiya_matn_save,
)

from handlers.biriktirish import (
    admin_biriktirish,
    biriktir_list_cb, biriktir_new_cb, biriktir_agent_cb,
    biriktir_back_cb, biriktir_change_cb, biriktir_rm_cb,
    biriktir_block_cb, biriktir_edit_field_cb,
    biriktir_edit_value_handler, biriktir_checker_cb,
)

from handlers.klient import (
    new_client_command,
    klient_rasm, klient_firma_nomi, klient_telefon1, klient_telefon2,
    klient_inn, klient_orienter, klient_lokatsiya, klient_lokatsiya_hint,
    klient_kategoriya, klient_dokon_turi, klient_distributor, klient_agent_kod,
    klient_chastota,
    klient_limit, klient_confirm, klient_edit_value,
    admin_klientlar, klient_reject_reason,
    klient_view_callback, klient_approve_callback, klient_reject_callback,
    mening_klientlarim_handler, mk_page_cb, mk_view_cb,
)

from handlers.callbacks import callback_handler

from handlers.faq import faq_start, faq_callback
from handlers.chat import matn_javob_handler
