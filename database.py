"""
Ma'lumotlar bazasi qatlami — Django ORM orqali.

Barcha funksiya imzolari avvalgi aiosqlite versiyasi bilan bir xil saqlanadi,
shuning uchun handlerlar o'zgarishsiz ishlaydi.
"""
from __future__ import annotations

from datetime import datetime

from asgiref.sync import sync_to_async
from django.db import connection

from config import GROUP_TIMEOUT_SEC, ADMIN_ID


# ── Lazy model import (Django setup dan keyin) ───────────────────────────────
def _models():
    from bot_app.models import (
        Xodim, Xabar, XabarGuruhi, FaqKategoriya, Faq,
        Baholash, CheckerFaollik, Biriktirish, AdminMsgMap,
        Klient, Sorov, SupervisorGroup, AdminUser, AuditLog, Instruksiya,
    )
    return (
        Xodim, Xabar, XabarGuruhi, FaqKategoriya, Faq,
        Baholash, CheckerFaollik, Biriktirish, AdminMsgMap,
        Klient, Sorov, SupervisorGroup, AdminUser, AuditLog, Instruksiya,
    )


# ── Raw SQL yordamchi ─────────────────────────────────────────────────────────
async def _raw_one(sql: str, params=None):
    def _run():
        with connection.cursor() as cur:
            cur.execute(sql, params or [])
            return cur.fetchone()
    return await sync_to_async(_run)()


async def _raw_all(sql: str, params=None) -> list:
    def _run():
        with connection.cursor() as cur:
            cur.execute(sql, params or [])
            return cur.fetchall()
    return await sync_to_async(_run)()


# ── DB versiyasi (stub — Django migratsiyalar boshqaradi) ────────────────────
async def get_db_version() -> int:
    return 1


async def set_db_version(version: int) -> None:
    pass


# ── init_db (Django migratsiyalar manage.py migrate orqali bajariladi) ───────
async def init_db():
    """
    Jadvallar manage.py migrate orqali yaratiladi.
    Bu funksiya faqat xotira keshini to'ldiradi.
    """
    await _reload_admin_cache()


# ── Adminlar keshi ────────────────────────────────────────────────────────────
_admin_cache: set[int] = set()


async def _reload_admin_cache() -> None:
    (_, _, _, _, _, _, _, _, _, _, _, _, AdminUser, _, _) = _models()
    ids = [r async for r in AdminUser.objects.values_list("user_id", flat=True)]
    _admin_cache.clear()
    _admin_cache.update(ids)


async def get_admins() -> list[int]:
    if not _admin_cache:
        await _reload_admin_cache()
    return list(_admin_cache)


async def is_admin(user_id: int) -> bool:
    if not _admin_cache:
        await _reload_admin_cache()
    return user_id in _admin_cache


async def add_admin(user_id: int) -> None:
    (_, _, _, _, _, _, _, _, _, _, _, _, AdminUser, _, _) = _models()
    await AdminUser.objects.aget_or_create(user_id=user_id)
    _admin_cache.add(user_id)


async def remove_admin(user_id: int) -> None:
    if user_id == ADMIN_ID:
        return
    (_, _, _, _, _, _, _, _, _, _, _, _, AdminUser, _, _) = _models()
    await AdminUser.objects.filter(user_id=user_id).adelete()
    _admin_cache.discard(user_id)


# ── Xodim ─────────────────────────────────────────────────────────────────────
async def get_xodim(user_id: int) -> tuple | None:
    """Returns (status, topic_id, ism, lavozim, filial, kod)"""
    (Xodim, *_) = _models()
    try:
        x = await Xodim.objects.aget(user_id=user_id)
        return (x.status, x.topic_id, x.ism, x.lavozim, x.filial, x.kod)
    except Xodim.DoesNotExist:
        return None


async def insert_xodim(user_id, ism, lavozim, kod, filial,
                       telefon1, telefon2, tugilgan_kun):
    (Xodim, *_) = _models()
    sana = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await Xodim.objects.aupdate_or_create(
        user_id=user_id,
        defaults=dict(
            ism=ism, lavozim=lavozim, kod=kod, filial=filial,
            telefon1=telefon1, telefon2=telefon2, tugilgan_kun=tugilgan_kun,
            topic_id=None, status="pending", sana=sana,
        ),
    )


async def approve_xodim(user_id: int, topic_id: int):
    (Xodim, *_) = _models()
    await Xodim.objects.filter(user_id=user_id).aupdate(status="approved", topic_id=topic_id)


async def clear_topic_id(user_id: int):
    (Xodim, *_) = _models()
    await Xodim.objects.filter(user_id=user_id).aupdate(topic_id=None)


async def reject_xodim(user_id: int):
    (Xodim, *_) = _models()
    await Xodim.objects.filter(user_id=user_id).aupdate(status="rejected")


async def block_xodim(user_id: int):
    (Xodim, *_) = _models()
    await Xodim.objects.filter(user_id=user_id).aupdate(status="blocked", topic_id=None)


async def unblock_xodim(user_id: int):
    (Xodim, *_) = _models()
    await Xodim.objects.filter(user_id=user_id).aupdate(status="approved")


async def reset_topic(user_id: int):
    (Xodim, *_) = _models()
    await Xodim.objects.filter(user_id=user_id).aupdate(status="pending", topic_id=None)


async def delete_xodim(user_id: int):
    (Xodim, *_) = _models()
    await Xodim.objects.filter(user_id=user_id).adelete()


async def update_xodim_field(user_id: int, field: str, value: str):
    allowed = {"ism", "lavozim", "kod", "filial"}
    if field not in allowed:
        raise ValueError(f"Ruxsat etilmagan maydon: {field}")
    (Xodim, *_) = _models()
    await Xodim.objects.filter(user_id=user_id).aupdate(**{field: value})


# ── Biriktirish ───────────────────────────────────────────────────────────────
async def get_biriktirish(agent_id: int) -> int | None:
    (_, _, _, _, _, _, _, Biriktirish, *_) = _models()
    try:
        b = await Biriktirish.objects.aget(agent_id=agent_id)
        return b.checker_id
    except Biriktirish.DoesNotExist:
        return None


async def set_biriktirish(agent_id: int, checker_id: int):
    (_, _, _, _, _, _, _, Biriktirish, *_) = _models()
    await Biriktirish.objects.aupdate_or_create(
        agent_id=agent_id,
        defaults={"checker_id": checker_id},
    )


async def delete_biriktirish(agent_id: int):
    (_, _, _, _, _, _, _, Biriktirish, *_) = _models()
    await Biriktirish.objects.filter(agent_id=agent_id).adelete()


async def get_all_biriktirish() -> list:
    """Returns [(agent_id, agent_ism, checker_id, checker_ism)]"""
    return await _raw_all("""
        SELECT b.agent_id, a.ism, b.checker_id, c.ism
        FROM biriktirish b
        LEFT JOIN xodimlar a ON a.user_id = b.agent_id
        LEFT JOIN xodimlar c ON c.user_id = b.checker_id
    """)


async def get_agents() -> list:
    (Xodim, *_) = _models()
    return [row async for row in Xodim.objects.filter(
        lavozim="Agent", status="approved"
    ).values_list("ism", "lavozim", "filial", "kod", "user_id", "status")]


async def get_available_checkers() -> list:
    (Xodim, *_) = _models()
    return [row async for row in Xodim.objects.filter(
        lavozim__in=["Supervisor", "Filial Rahbari", "Distribyutor"],
        status="approved",
    ).values_list("ism", "lavozim", "filial", "kod", "user_id", "status")]


async def get_distributors() -> list:
    (Xodim, *_) = _models()
    return [row async for row in Xodim.objects.filter(
        lavozim="Distribyutor", status="approved"
    ).values_list("ism", "lavozim", "filial", "kod", "user_id", "status")]


async def get_xodim_full(user_id: int) -> tuple | None:
    """Returns (user_id, ism, lavozim, kod, filial, tel1, tel2, tug_kun, topic_id, status, sana)"""
    (Xodim, *_) = _models()
    try:
        x = await Xodim.objects.aget(user_id=user_id)
        return (x.user_id, x.ism, x.lavozim, x.kod, x.filial,
                x.telefon1, x.telefon2, x.tugilgan_kun, x.topic_id, x.status, x.sana)
    except Xodim.DoesNotExist:
        return None


async def search_xodimlar(query: str) -> list:
    (Xodim, *_) = _models()
    if query.isdigit():
        return [row async for row in Xodim.objects.filter(
            user_id=int(query)
        ).values_list("ism", "lavozim", "filial", "kod", "user_id", "status")]
    return [row async for row in Xodim.objects.filter(
        ism__icontains=query
    ).values_list("ism", "lavozim", "filial", "kod", "user_id", "status")]


async def get_approved_xodimlar() -> list:
    (Xodim, *_) = _models()
    return [row async for row in Xodim.objects.filter(
        status="approved"
    ).values_list("ism", "lavozim", "filial", "kod", "user_id")]


async def get_pending_xodimlar() -> list:
    (Xodim, *_) = _models()
    return [row async for row in Xodim.objects.filter(
        status="pending"
    ).values_list("user_id", "ism", "lavozim", "kod", "filial")]


async def get_pending_sorovlar_count() -> int:
    (_, _, _, _, _, _, _, _, _, _, Sorov, *_) = _models()
    return await Sorov.objects.filter(status="pending_supervisor").acount()


async def get_pending_sorovlar_by_supervisor() -> dict[int, int]:
    return dict(await _raw_all("""
        SELECT supervisor_id, COUNT(*) FROM sorovlar
        WHERE status='pending_supervisor' AND supervisor_id IS NOT NULL
        AND supervisor_id NOT IN (SELECT user_id FROM admins)
        GROUP BY supervisor_id
    """))


async def get_pending_sorovlar_for_push() -> list[tuple]:
    return await _raw_all("""
        SELECT supervisor_id, id, sup_msg_id FROM sorovlar
        WHERE status='pending_supervisor' AND supervisor_id IS NOT NULL
        AND supervisor_id NOT IN (SELECT user_id FROM admins)
        ORDER BY supervisor_id, id
    """)


async def get_blocked_xodimlar() -> list:
    (Xodim, *_) = _models()
    return [row async for row in Xodim.objects.filter(
        status="blocked"
    ).values_list("user_id", "ism", "lavozim", "filial", "kod")]


async def get_all_xodimlar_for_excel() -> list:
    (Xodim, *_) = _models()
    return [row async for row in Xodim.objects.all().values_list(
        "user_id", "ism", "lavozim", "kod", "filial",
        "telefon1", "telefon2", "tugilgan_kun", "status", "sana"
    )]


# ── Xabar guruhi ──────────────────────────────────────────────────────────────
async def create_xabar_guruhi(user_id: int, ism: str, filial: str, topic_id: int) -> int:
    (_, _, XabarGuruhi, *_) = _models()
    vaqt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    g = await XabarGuruhi.objects.acreate(
        user_id=user_id, ism=ism, filial=filial, topic_id=topic_id,
        holat="kutilmoqda", vaqt=vaqt,
    )
    return g.pk


async def get_active_group(user_id: int) -> tuple | None:
    return await _raw_one(f"""
        SELECT g.id, g.topic_id
        FROM xabar_guruhi g
        WHERE g.user_id = %s AND g.holat = 'kutilmoqda'
        AND (
            SELECT MAX(x.vaqt) FROM xabarlar x WHERE x.group_id = g.id
        ) >= datetime('now', 'localtime', '-{GROUP_TIMEOUT_SEC} seconds')
        ORDER BY g.id DESC LIMIT 1
    """, [user_id])


async def get_group_info(group_id: int) -> tuple | None:
    (_, _, XabarGuruhi, *_) = _models()
    try:
        g = await XabarGuruhi.objects.aget(pk=group_id)
        return (g.user_id, g.ism, g.filial, g.topic_id, g.holat)
    except XabarGuruhi.DoesNotExist:
        return None


async def update_group_holat(group_id: int, holat: str):
    (_, Xabar, XabarGuruhi, *_) = _models()
    if holat == "bajarildi":
        javob_vaqt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await XabarGuruhi.objects.filter(pk=group_id).aupdate(holat=holat, javob_vaqt=javob_vaqt)
        await Xabar.objects.filter(group_id=group_id).aupdate(holat=holat, javob_vaqt=javob_vaqt)
    else:
        await XabarGuruhi.objects.filter(pk=group_id).aupdate(holat=holat)
        await Xabar.objects.filter(group_id=group_id).aupdate(holat=holat)


async def get_most_important_msg(group_id: int) -> tuple | None:
    return await _raw_one("""
        SELECT id, xabar_turi, msg_id,
               CASE xabar_turi
                   WHEN '📷 Rasm'         THEN 1
                   WHEN '🎥 Video'         THEN 2
                   WHEN '⭕ Video-xabar'   THEN 3
                   WHEN '📄 Fayl'          THEN 4
                   WHEN '🎙 Ovozli xabar'  THEN 5
                   WHEN '🎭 Sticker'       THEN 6
                   ELSE                        7
               END AS priority
        FROM xabarlar WHERE group_id = %s
        ORDER BY priority ASC, id DESC
        LIMIT 1
    """, [group_id])


async def count_group_msgs(group_id: int) -> int:
    (_, Xabar, *_) = _models()
    return await Xabar.objects.filter(group_id=group_id).acount()


async def get_group_msgs_list(group_id: int) -> list:
    (_, Xabar, *_) = _models()
    return [row async for row in Xabar.objects.filter(
        group_id=group_id
    ).order_by("id").values_list("xabar_turi", "vaqt")]


# ── Xabar ─────────────────────────────────────────────────────────────────────
async def insert_xabar(user_id, ism, filial, xabar_turi, msg_id, group_id=None) -> int:
    (_, Xabar, *_) = _models()
    vaqt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    x = await Xabar.objects.acreate(
        user_id=user_id, xodim_name=ism, filial=filial,
        xabar_turi=xabar_turi, vaqt=vaqt, holat="kutilmoqda",
        msg_id=msg_id, group_id=group_id,
    )
    return x.pk


async def update_xabar_group_fwd_id(task_id: int, group_fwd_id: int):
    (_, Xabar, *_) = _models()
    await Xabar.objects.filter(pk=task_id).aupdate(group_fwd_id=group_fwd_id)


async def get_xabar_by_group_fwd_id(group_fwd_id: int) -> tuple | None:
    (_, Xabar, *_) = _models()
    x = await Xabar.objects.filter(group_fwd_id=group_fwd_id).values_list(
        "user_id", "msg_id"
    ).afirst()
    return x


async def insert_admin_msg_map(user_id: int, group_msg_id: int, private_msg_id: int):
    (_, _, _, _, _, _, _, _, AdminMsgMap, *_) = _models()
    await AdminMsgMap.objects.acreate(
        user_id=user_id, group_msg_id=group_msg_id, private_msg_id=private_msg_id,
    )


async def get_group_msg_id_by_private(user_id: int, private_msg_id: int) -> int | None:
    (_, _, _, _, _, _, _, _, AdminMsgMap, *_) = _models()
    row = await AdminMsgMap.objects.filter(
        user_id=user_id, private_msg_id=private_msg_id
    ).values_list("group_msg_id", flat=True).afirst()
    return row


async def get_private_msg_id_by_group(user_id: int, group_msg_id: int) -> int | None:
    (_, _, _, _, _, _, _, _, AdminMsgMap, *_) = _models()
    row = await AdminMsgMap.objects.filter(
        user_id=user_id, group_msg_id=group_msg_id
    ).values_list("private_msg_id", flat=True).afirst()
    return row


async def get_xodim_by_topic(topic_id: int) -> tuple | None:
    (Xodim, *_) = _models()
    x = await Xodim.objects.filter(
        topic_id=topic_id, status="approved"
    ).values_list("user_id", "ism").afirst()
    return x


async def get_xabar(task_id: int) -> tuple | None:
    """Returns (user_id, xodim_name, msg_id, holat)"""
    (_, Xabar, *_) = _models()
    try:
        x = await Xabar.objects.aget(pk=task_id)
        return (x.user_id, x.xodim_name, x.msg_id, x.holat)
    except Xabar.DoesNotExist:
        return None


async def update_xabar_holat(task_id: int, holat: str):
    (_, Xabar, *_) = _models()
    if holat == "bajarildi":
        javob_vaqt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await Xabar.objects.filter(pk=task_id).aupdate(holat=holat, javob_vaqt=javob_vaqt)
    else:
        await Xabar.objects.filter(pk=task_id).aupdate(holat=holat)


async def get_all_xabarlar_for_excel() -> list:
    (_, Xabar, *_) = _models()
    return [row async for row in Xabar.objects.all().values_list(
        "id", "user_id", "xodim_name", "filial", "xabar_turi", "vaqt", "holat", "javob_vaqt"
    )]


async def get_kunlik_statistika() -> list:
    return await _raw_all("""
        SELECT ism, filial,
               COUNT(*) AS jami,
               SUM(CASE WHEN holat='bajarildi' THEN 1 ELSE 0 END) AS bajarildi
        FROM xabar_guruhi
        WHERE date(vaqt) = date('now', 'localtime')
        GROUP BY user_id
        ORDER BY jami DESC
    """)


async def get_statistika() -> dict:
    g = await _raw_one(
        "SELECT COUNT(*), SUM(CASE WHEN holat='bajarildi' THEN 1 ELSE 0 END) FROM xabar_guruhi"
    )
    m = await _raw_one(
        "SELECT COUNT(*), SUM(CASE WHEN holat='bajarildi' THEN 1 ELSE 0 END) FROM xabarlar WHERE group_id IS NULL"
    )
    times = await _raw_all("""
        SELECT vaqt, javob_vaqt FROM xabar_guruhi WHERE holat='bajarildi'
        UNION ALL
        SELECT vaqt, javob_vaqt FROM xabarlar WHERE holat='bajarildi' AND group_id IS NULL
    """)

    g_jami, g_baj = g[0] or 0, g[1] or 0
    m_jami, m_baj = m[0] or 0, m[1] or 0
    jami = g_jami + m_jami
    bajarilgan = g_baj + m_baj
    total_min = 0.0
    for t_kir, t_baj in times:
        try:
            d1 = datetime.strptime(t_kir, "%Y-%m-%d %H:%M:%S")
            d2 = datetime.strptime(t_baj, "%Y-%m-%d %H:%M:%S")
            total_min += (d2 - d1).total_seconds() / 60
        except Exception:
            continue
    ortacha = round(total_min / bajarilgan, 1) if bajarilgan > 0 else 0.0
    return {
        "jami": jami,
        "bajarilgan": bajarilgan,
        "kutilmoqda": jami - bajarilgan,
        "ortacha": ortacha,
    }


# ── FAQ ───────────────────────────────────────────────────────────────────────
async def get_faq_kategoriyalar() -> list:
    (_, _, _, FaqKategoriya, *_) = _models()
    return [row async for row in FaqKategoriya.objects.order_by(
        "tartib", "id"
    ).values_list("id", "emoji", "nomi")]


async def get_faq_savollar(kategoriya_id: int) -> list:
    (_, _, _, _, Faq, *_) = _models()
    return [row async for row in Faq.objects.filter(
        kategoriya_id=kategoriya_id
    ).order_by("tartib", "id").values_list("id", "savol")]


async def get_faq_item(faq_id: int) -> tuple | None:
    (_, _, _, _, Faq, *_) = _models()
    try:
        f = await Faq.objects.aget(pk=faq_id)
        return (f.savol, f.javob, f.kategoriya_id)
    except Faq.DoesNotExist:
        return None


async def add_faq_kategoriya(emoji: str, nomi: str) -> int:
    (_, _, _, FaqKategoriya, *_) = _models()
    k = await FaqKategoriya.objects.acreate(emoji=emoji, nomi=nomi)
    return k.pk


async def add_faq(kategoriya_id: int, savol: str, javob: str) -> int:
    (_, _, _, _, Faq, *_) = _models()
    f = await Faq.objects.acreate(kategoriya_id=kategoriya_id, savol=savol, javob=javob)
    return f.pk


async def delete_faq(faq_id: int):
    (_, _, _, _, Faq, *_) = _models()
    await Faq.objects.filter(pk=faq_id).adelete()


async def delete_faq_kategoriya(kategoriya_id: int):
    (_, _, _, FaqKategoriya, Faq, *_) = _models()
    await Faq.objects.filter(kategoriya_id=kategoriya_id).adelete()
    await FaqKategoriya.objects.filter(pk=kategoriya_id).adelete()


# ── Urgency ───────────────────────────────────────────────────────────────────
async def set_urgency(group_id: int, urgency: str):
    (_, _, XabarGuruhi, *_) = _models()
    await XabarGuruhi.objects.filter(pk=group_id).aupdate(urgency=urgency)


async def get_group_urgency(group_id: int) -> str | None:
    (_, _, XabarGuruhi, *_) = _models()
    row = await XabarGuruhi.objects.filter(pk=group_id).values_list(
        "urgency", flat=True
    ).afirst()
    return row


# ── Baholash ──────────────────────────────────────────────────────────────────
async def add_baholash(group_id: int, checker_id: int, agent_id: int, yulduz: int):
    (_, _, _, _, _, Baholash, *_) = _models()
    vaqt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await Baholash.objects.aupdate_or_create(
        group_id=group_id,
        defaults={"checker_id": checker_id, "agent_id": agent_id, "yulduz": yulduz, "vaqt": vaqt},
    )


async def get_agent_rating_summary(agent_id: int) -> dict:
    row = await _raw_one(
        "SELECT ROUND(AVG(yulduz),1), COUNT(*) FROM baholash WHERE agent_id=%s",
        [agent_id],
    )
    haftalik_row = await _raw_one(
        "SELECT ROUND(AVG(yulduz),1) FROM baholash WHERE agent_id=%s AND date(vaqt)>=date('now','-7 days','localtime')",
        [agent_id],
    )
    avg, total = (row[0] or 0.0), (row[1] or 0)
    haftalik = haftalik_row[0] or 0.0
    return {"avg": avg, "total": total, "haftalik": haftalik}


async def get_agent_leaderboard() -> list:
    return await _raw_all("""
        SELECT x.user_id, x.ism, x.filial,
               ROUND(AVG(b.yulduz),1) as avg_r,
               COUNT(b.id) as total,
               ROUND(AVG(CASE WHEN date(b.vaqt) >= date('now','-7 days','localtime') THEN b.yulduz END),1) as haftalik
        FROM xodimlar x
        JOIN baholash b ON b.agent_id = x.user_id
        WHERE x.lavozim='Agent' AND x.status='approved'
        GROUP BY x.user_id
        ORDER BY avg_r DESC, total DESC
    """)


# ── Checker faollik ────────────────────────────────────────────────────────────
async def update_checker_faollik(checker_id: int):
    (_, _, _, _, _, _, CheckerFaollik, *_) = _models()
    vaqt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await CheckerFaollik.objects.aupdate_or_create(
        checker_id=checker_id,
        defaults={"last_active": vaqt},
    )


async def get_checker_faollik(checker_id: int) -> str | None:
    (_, _, _, _, _, _, CheckerFaollik, *_) = _models()
    row = await CheckerFaollik.objects.filter(
        checker_id=checker_id
    ).values_list("last_active", flat=True).afirst()
    return row


# ── Haftalik hisobot ──────────────────────────────────────────────────────────
async def get_checker_weekly_stats() -> list:
    return await _raw_all("""
        SELECT c.ism,
               COUNT(DISTINCT bir.agent_id) as agents,
               COUNT(DISTINCT g.id) as topshiriq,
               SUM(CASE WHEN g.holat='bajarildi' THEN 1 ELSE 0 END) as bajarildi,
               ROUND(AVG(b.yulduz),1) as avg_r
        FROM biriktirish bir
        JOIN xodimlar c ON c.user_id = bir.checker_id
        LEFT JOIN xabar_guruhi g ON g.user_id = bir.agent_id
            AND date(g.vaqt) >= date('now','-7 days','localtime')
        LEFT JOIN baholash b ON b.agent_id = bir.agent_id
            AND date(b.vaqt) >= date('now','-7 days','localtime')
        GROUP BY bir.checker_id
        ORDER BY bajarildi DESC
    """)


async def get_agents_without_messages_today() -> list:
    return await _raw_all("""
        SELECT x.user_id, x.ism FROM xodimlar x
        WHERE x.lavozim='Agent' AND x.status='approved'
        AND x.user_id NOT IN (
            SELECT DISTINCT user_id FROM xabar_guruhi
            WHERE date(vaqt) = date('now','localtime')
        )
    """)


# ── Filial statistikasi ────────────────────────────────────────────────────────
async def get_filial_stats(period: str = "haftalik") -> list:
    period_filter = {
        "haftalik": "date('now','-7 days','localtime')",
        "oylik":    "date('now','-30 days','localtime')",
        "yillik":   "date('now','-365 days','localtime')",
        "hammasi":  "date('2000-01-01')",
    }.get(period, "date('now','-7 days','localtime')")

    return await _raw_all(f"""
        SELECT
            x.filial,
            COUNT(DISTINCT x.user_id)                                          as agent_soni,
            COUNT(DISTINCT g.id)                                               as topshiriq,
            SUM(CASE WHEN g.holat='bajarildi' THEN 1 ELSE 0 END)              as bajarildi,
            ROUND(AVG(b.yulduz), 1)                                            as avg_reyting,
            ROUND(AVG(CASE
                WHEN g.holat='bajarildi' AND g.javob_vaqt IS NOT NULL
                THEN (julianday(g.javob_vaqt) - julianday(g.vaqt)) * 1440
            END), 1)                                                            as avg_vaqt
        FROM xodimlar x
        LEFT JOIN xabar_guruhi g
            ON g.user_id = x.user_id AND date(g.vaqt) >= {period_filter}
        LEFT JOIN baholash b
            ON b.agent_id = x.user_id AND date(b.vaqt) >= {period_filter}
        WHERE x.lavozim='Agent' AND x.status='approved'
        GROUP BY x.filial
        ORDER BY bajarildi DESC, avg_reyting DESC
    """)


async def get_agent_today_stats(agent_id: int) -> dict:
    row = await _raw_one("""
        SELECT COUNT(*), SUM(CASE WHEN holat='bajarildi' THEN 1 ELSE 0 END)
        FROM xabar_guruhi
        WHERE user_id=%s AND date(vaqt)=date('now','localtime')
    """, [agent_id])
    return {"bugun": row[0] or 0, "bajarildi": row[1] or 0}


async def get_unassigned_agents() -> list:
    return await _raw_all("""
        SELECT x.ism, x.user_id, x.filial, x.kod
        FROM xodimlar x
        WHERE x.lavozim='Agent' AND x.status='approved'
        AND x.user_id NOT IN (SELECT agent_id FROM biriktirish)
    """)


async def get_latest_group_fwd_id(group_id: int) -> int | None:
    (_, Xabar, *_) = _models()
    row = await Xabar.objects.filter(
        group_id=group_id, group_fwd_id__isnull=False
    ).order_by("-id").values_list("group_fwd_id", flat=True).afirst()
    return row


async def get_all_biriktirish_detailed() -> list:
    return await _raw_all("""
        SELECT b.agent_id, a.ism, b.checker_id, c.ism, a.filial, a.status
        FROM biriktirish b
        JOIN xodimlar a ON a.user_id = b.agent_id
        LEFT JOIN xodimlar c ON c.user_id = b.checker_id
        ORDER BY a.ism
    """)


# ── Klientlar ─────────────────────────────────────────────────────────────────
async def insert_klient(rasm_file_id, firma_nomi, telefon1, telefon2, inn, orienter,
                        lokatsiya_lat, lokatsiya_lon, lokatsiya_address, kategoriya, dokon_turi,
                        distributor, agent_kod, vizit_kun, chastota, limit_summa, brendlar,
                        supervisor_id) -> int:
    (_, _, _, _, _, _, _, _, _, Klient, *_) = _models()
    sana = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    k = await Klient.objects.acreate(
        rasm_file_id=rasm_file_id, firma_nomi=firma_nomi, telefon1=telefon1,
        telefon2=telefon2, inn=inn, orienter=orienter,
        lokatsiya_lat=lokatsiya_lat, lokatsiya_lon=lokatsiya_lon,
        lokatsiya_address=lokatsiya_address, kategoriya=kategoriya,
        dokon_turi=dokon_turi, distributor=distributor, agent_kod=agent_kod,
        vizit_kun=vizit_kun, chastota=chastota, limit_summa=limit_summa,
        brendlar=brendlar, status="pending", sana=sana, supervisor_id=supervisor_id,
    )
    return k.pk


async def get_klient(klient_id: int) -> tuple | None:
    (_, _, _, _, _, _, _, _, _, Klient, *_) = _models()
    try:
        return (await Klient.objects.aget(pk=klient_id)).as_tuple()
    except Klient.DoesNotExist:
        return None


async def get_klientlar_by_supervisor(supervisor_id: int) -> list:
    (_, _, _, _, _, _, _, _, _, Klient, *_) = _models()
    return [k.as_tuple() async for k in Klient.objects.filter(
        supervisor_id=supervisor_id
    ).order_by("-sana")]


async def get_all_klientlar(status: str | None = None) -> list:
    (_, _, _, _, _, _, _, _, _, Klient, *_) = _models()
    qs = Klient.objects.filter(status=status) if status else Klient.objects.all()
    return [k.as_tuple() async for k in qs.order_by("-sana")]


async def approve_klient(klient_id: int):
    (_, _, _, _, _, _, _, _, _, Klient, *_) = _models()
    await Klient.objects.filter(pk=klient_id).aupdate(status="approved")


async def reject_klient(klient_id: int, reason: str):
    (_, _, _, _, _, _, _, _, _, Klient, *_) = _models()
    await Klient.objects.filter(pk=klient_id).aupdate(status="rejected", reject_reason=reason)


async def search_klientlar(query: str) -> list:
    digits = "".join(filter(str.isdigit, query))
    if len(digits) == 12 and digits.startswith("998"):
        phone_q = digits[3:]
    elif len(digits) == 10 and digits.startswith("0"):
        phone_q = digits[1:]
    elif len(digits) >= 9:
        phone_q = digits[-9:]
    else:
        phone_q = digits

    rows = await _raw_all("""
        SELECT * FROM klientlar
        WHERE firma_nomi LIKE %s
           OR inn LIKE %s
           OR distributor LIKE %s
           OR REPLACE(REPLACE(telefon1, '+', ''), ' ', '') LIKE %s
           OR REPLACE(REPLACE(telefon2, '+', ''), ' ', '') LIKE %s
        ORDER BY sana DESC
    """, [f"%{query}%", f"%{query}%", f"%{query}%",
          f"%{phone_q}%", f"%{phone_q}%"])
    return rows


async def get_all_klientlar_for_excel() -> list:
    (_, _, _, _, _, _, _, _, _, Klient, *_) = _models()
    return [k.as_tuple() async for k in Klient.objects.filter(status="approved").order_by("firma_nomi")]


async def get_klientlar_stats() -> dict:
    rows = await _raw_all(
        "SELECT status, COUNT(*) FROM klientlar GROUP BY status"
    )
    stats = {"pending": 0, "approved": 0, "rejected": 0}
    for status, count in rows:
        if status in stats:
            stats[status] = count
    stats["total"] = sum(stats.values())
    return stats


async def get_opened_klientlar_for_excel() -> list:
    return await _raw_all("""
        SELECT id, firma_nomi, telefon1, telefon2, inn, orienter,
               lokatsiya_lat, lokatsiya_lon, lokatsiya_address,
               kategoriya, dokon_turi, distributor, agent_kod,
               limit_summa, brendlar, status, sana, supervisor_id
        FROM klientlar
        WHERE status IN ('pending', 'approved')
        ORDER BY sana DESC
    """)


async def check_duplicate_firma(firma_nomi: str) -> dict | None:
    row = await _raw_one(
        "SELECT * FROM klientlar WHERE LOWER(firma_nomi) = LOWER(%s) LIMIT 1",
        [firma_nomi],
    )
    if row:
        cols = ("id", "rasm", "firma_nomi", "telefon1", "telefon2", "inn", "orienter",
                "lat", "lon", "kategoriya", "dokon_turi", "distributor", "agent_kod",
                "vizit_kun", "chastota", "limit", "brendlar", "status", "reason", "sana",
                "sup_id", "lokatsiya_address")
        return dict(zip(cols, row))
    return None


async def check_duplicate_telefon(telefon: str) -> dict | None:
    row = await _raw_one(
        "SELECT * FROM klientlar WHERE telefon1 = %s OR telefon2 = %s LIMIT 1",
        [telefon, telefon],
    )
    if row:
        cols = ("id", "rasm", "firma_nomi", "telefon1", "telefon2", "inn", "orienter",
                "lat", "lon", "kategoriya", "dokon_turi", "distributor", "agent_kod",
                "vizit_kun", "chastota", "limit", "brendlar", "status", "reason", "sana",
                "sup_id", "lokatsiya_address")
        return dict(zip(cols, row))
    return None


# ── Sorovlar ──────────────────────────────────────────────────────────────────
async def insert_sorov(agent_id: int, agent_ism: str, tur: str,
                       dokon_nomi: str | None, yangi_qiymat: str | None,
                       lat: float | None, lon: float | None,
                       foto_ids: str | None, izoh: str | None,
                       supervisor_id: int | None) -> int:
    (_, _, _, _, _, _, _, _, _, _, Sorov, *_) = _models()
    sana = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    s = await Sorov.objects.acreate(
        agent_id=agent_id, agent_ism=agent_ism, tur=tur,
        dokon_nomi=dokon_nomi, yangi_qiymat=yangi_qiymat,
        lat=lat, lon=lon, foto_ids=foto_ids, izoh=izoh,
        status="pending_supervisor" if supervisor_id else "pending_admin",
        supervisor_id=supervisor_id, sana=sana,
    )
    return s.pk


async def get_sorov(sorov_id: int) -> tuple | None:
    (_, _, _, _, _, _, _, _, _, _, Sorov, *_) = _models()
    try:
        return (await Sorov.objects.aget(pk=sorov_id)).as_tuple()
    except Sorov.DoesNotExist:
        return None


async def update_sorov_status(sorov_id: int, status: str) -> None:
    (_, _, _, _, _, _, _, _, _, _, Sorov, *_) = _models()
    await Sorov.objects.filter(pk=sorov_id).aupdate(status=status)


async def update_sorov_agent_msg_id(sorov_id: int, msg_id: int) -> None:
    (_, _, _, _, _, _, _, _, _, _, Sorov, *_) = _models()
    await Sorov.objects.filter(pk=sorov_id).aupdate(agent_msg_id=msg_id)


async def update_sorov_sup_msg_id(sorov_id: int, msg_id: int) -> None:
    (_, _, _, _, _, _, _, _, _, _, Sorov, *_) = _models()
    await Sorov.objects.filter(pk=sorov_id).aupdate(sup_msg_id=msg_id)


async def update_sorov_admin_msg_id(sorov_id: int, msg_id: int) -> None:
    (_, _, _, _, _, _, _, _, _, _, Sorov, *_) = _models()
    await Sorov.objects.filter(pk=sorov_id).aupdate(admin_msg_id=msg_id)


async def get_sorov_by_sup_msg_id(msg_id: int) -> tuple | None:
    (_, _, _, _, _, _, _, _, _, _, Sorov, *_) = _models()
    s = await Sorov.objects.filter(sup_msg_id=msg_id).afirst()
    return s.as_tuple() if s else None


async def get_sorov_by_admin_msg_id(msg_id: int) -> tuple | None:
    (_, _, _, _, _, _, _, _, _, _, Sorov, *_) = _models()
    s = await Sorov.objects.filter(admin_msg_id=msg_id).afirst()
    return s.as_tuple() if s else None


async def update_sorov_group_id(sorov_id: int, group_chat_id: int) -> None:
    (_, _, _, _, _, _, _, _, _, _, Sorov, *_) = _models()
    await Sorov.objects.filter(pk=sorov_id).aupdate(group_id=group_chat_id)


# ── Supervisor ↔ Group ─────────────────────────────────────────────────────────
async def set_supervisor_group(supervisor_id: int, group_chat_id: int) -> None:
    (_, _, _, _, _, _, _, _, _, _, _, SupervisorGroup, *_) = _models()
    await SupervisorGroup.objects.aupdate_or_create(
        supervisor_id=supervisor_id,
        defaults={"group_chat_id": group_chat_id},
    )


async def get_supervisor_group(supervisor_id: int) -> int | None:
    (_, _, _, _, _, _, _, _, _, _, _, SupervisorGroup, *_) = _models()
    row = await SupervisorGroup.objects.filter(
        supervisor_id=supervisor_id
    ).values_list("group_chat_id", flat=True).afirst()
    return row


async def delete_supervisor_group(supervisor_id: int) -> None:
    (_, _, _, _, _, _, _, _, _, _, _, SupervisorGroup, *_) = _models()
    await SupervisorGroup.objects.filter(supervisor_id=supervisor_id).adelete()


# ── Audit log ─────────────────────────────────────────────────────────────────
async def insert_audit_log(user_id: int, user_role: str, action_type: str,
                            target: str | None = None, old_value: str | None = None,
                            new_value: str | None = None, status: str | None = None,
                            request_id: int | None = None) -> None:
    (_, _, _, _, _, _, _, _, _, _, _, _, _, AuditLog, _) = _models()
    await AuditLog.objects.acreate(
        user_id=user_id, user_role=user_role, action_type=action_type,
        target=target, old_value=old_value, new_value=new_value,
        status=status, request_id=request_id,
    )


async def get_audit_logs(filter_type: str = "all", limit: int = 20) -> list:
    if filter_type == "agent":
        where = "WHERE a.user_role = 'agent'"
    elif filter_type == "supervisor":
        where = "WHERE a.user_role IN ('supervisor', 'filial_rahbari')"
    elif filter_type == "rejected":
        where = "WHERE a.status = 'rejected'"
    else:
        where = ""
    return await _raw_all(f"""
        SELECT a.id, a.user_id, a.user_role, a.action_type, a.target,
               a.old_value, a.new_value, a.status, a.request_id, a.created_at,
               x.ism
        FROM audit_log a
        LEFT JOIN xodimlar x ON x.user_id = a.user_id
        {where}
        ORDER BY a.id DESC LIMIT %s
    """, [limit])


# ── Instruksiyalar ────────────────────────────────────────────────────────────
async def get_instruksiya(lavozim: str) -> tuple | None:
    (_, _, _, _, _, _, _, _, _, _, _, _, _, _, Instruksiya) = _models()
    try:
        i = await Instruksiya.objects.aget(lavozim=lavozim)
        return (i.matn, i.media_type, i.media_file_id)
    except Instruksiya.DoesNotExist:
        return None


async def set_instruksiya(lavozim: str, matn: str | None,
                          media_type: str | None = None,
                          media_file_id: str | None = None) -> None:
    (_, _, _, _, _, _, _, _, _, _, _, _, _, _, Instruksiya) = _models()
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await Instruksiya.objects.aupdate_or_create(
        lavozim=lavozim,
        defaults={"matn": matn, "media_type": media_type,
                  "media_file_id": media_file_id, "updated_at": updated_at},
    )


# ── Excel export ───────────────────────────────────────────────────────────────
async def get_xabar_guruhi_for_excel() -> list:
    (_, _, XabarGuruhi, *_) = _models()
    return [row async for row in XabarGuruhi.objects.order_by("-id").values_list(
        "id", "user_id", "ism", "filial", "topic_id", "holat", "urgency", "vaqt", "javob_vaqt"
    )]


async def get_sorovlar_for_excel() -> list:
    (_, _, _, _, _, _, _, _, _, _, Sorov, *_) = _models()
    return [row async for row in Sorov.objects.order_by("-id").values_list(
        "id", "agent_id", "agent_ism", "tur", "dokon_nomi", "yangi_qiymat",
        "lat", "lon", "izoh", "status", "sana"
    )]


async def get_baholash_for_excel() -> list:
    return await _raw_all("""
        SELECT b.id, b.group_id,
               b.checker_id, c.ism AS checker_ism,
               b.agent_id,  a.ism AS agent_ism,
               b.yulduz, b.vaqt
        FROM baholash b
        LEFT JOIN xodimlar c ON c.user_id = b.checker_id
        LEFT JOIN xodimlar a ON a.user_id = b.agent_id
        ORDER BY b.id DESC
    """)


async def get_audit_log_for_excel() -> list:
    return await _raw_all("""
        SELECT a.id, a.user_id, x.ism, a.user_role, a.action_type,
               a.target, a.old_value, a.new_value, a.status, a.created_at
        FROM audit_log a
        LEFT JOIN xodimlar x ON x.user_id = a.user_id
        ORDER BY a.id DESC
    """)


async def get_all_klientlar_full_for_excel() -> list:
    return await _raw_all("""
        SELECT id, firma_nomi, telefon1, telefon2, inn, orienter,
               lokatsiya_lat, lokatsiya_lon, lokatsiya_address,
               kategoriya, dokon_turi, distributor, agent_kod,
               vizit_kun, chastota, limit_summa, brendlar,
               status, reject_reason, sana, supervisor_id
        FROM klientlar ORDER BY id DESC
    """)


async def get_full_db_for_excel() -> dict:
    xodimlar    = await get_all_xodimlar_for_excel()
    sorovlar    = await get_sorovlar_for_excel()
    klientlar   = await get_all_klientlar_full_for_excel()
    biriktirish = await get_all_biriktirish_detailed()
    baholash    = await get_baholash_for_excel()
    audit_log   = await get_audit_log_for_excel()
    return {
        "xodimlar":     xodimlar,
        "topshiriqlar": sorovlar,
        "klientlar":    klientlar,
        "sorovlar":     sorovlar,
        "biriktirish":  biriktirish,
        "baholash":     baholash,
        "audit_log":    audit_log,
    }
