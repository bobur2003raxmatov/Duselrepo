"""
handlers/ paketi — Dusel Company bot handler'lari.

Tuzilish:
  _core.py            — Barcha handler'lar (hozircha bitta fayl)
  _base.py            — Umumiy yordamchilar: em, rate_limited, admin_only, ...
  registration.py     — Ro'yxatdan o'tish oqimi
  xodim.py            — Xodim xabarlari, reaksiyalar
  callbacks.py        — Callback router va sub-handler'lar
  admin.py            — Admin panel: statistika, xodimlar, tarix
  biriktirish.py      — Agent↔Checker biriktirish
  reyting.py          — Reyting va filial leaderboard
  client.py           — Klient ro'yxatdan o'tkazish (16 qadam)
  admin_klientlar.py  — Admin klient boshqaruvi

Hozir barcha kod _core.py da joylashgan. Keyingi bosqichda yuqoridagi
sub-modullarga ajratiladi — bu fayl o'zgarmaydi.
"""

from handlers._core import (
    # Yordamchilar
    em, format_phone, safe_callback_int, rate_limited,
    admin_only, _role_keyboard,

    # Ro'yxatdan o'tish
    cancel, start,
    ism_olish, lavozim_olish, kod_olish,
    filial_olish, telefon_olish, telefon2_olish,
    tugilgan_kun_olish,

    # Xodim xabarlari
    xodim_chat_handler, reaction_handler, admin_guruh_javob,

    # Callback router
    callback_handler,

    # Admin panel
    admin_statistika, admin_xodimlar,
    _xodim_list_page_cb, _xodim_info_cb, _xodim_edit_cb, _xodim_search_start_cb,
    admin_kutilayotganlar, admin_bloklanganlar, admin_excel_eksport,
    edit_field, edit_value, search_query_handler,
    admin_tarix, tarix_filter_callback,

    # Biriktirish
    admin_biriktirish,
    biriktir_list_cb, biriktir_new_cb, biriktir_agent_cb,
    biriktir_back_cb, biriktir_change_cb, biriktir_rm_cb,
    biriktir_block_cb, biriktir_edit_field_cb,
    biriktir_edit_value_handler, biriktir_checker_cb,

    # Klient ro'yxatdan o'tkazish
    new_client_command,
    klient_rasm, klient_firma_nomi, klient_telefon1, klient_telefon2,
    klient_inn, klient_orienter, klient_lokatsiya, klient_lokatsiya_hint,
    klient_kategoriya, klient_dokon_turi, klient_distributor, klient_agent_kod,
    klient_chastota,
    klient_limit, klient_confirm, klient_edit_value,

    # Admin klientlar
    admin_klientlar, klient_reject_reason,

    # Topic o'chirilish va DB boshqaruvi
    topic_closed_handler,
    admin_upload_db,
    add_admin_command, add_admin_id_receive, admin_mgmt_callback,

    # Instruksiya
    instruksiya_cmd,
    admin_instruksiya_lavozim_cb,
    admin_instruksiya_edit_cb,
    admin_instruksiya_del_cb,
    admin_instruksiya_matn_save,
)
