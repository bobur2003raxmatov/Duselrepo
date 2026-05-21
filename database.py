import aiosqlite
from datetime import datetime
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS xodimlar (
                user_id      INTEGER PRIMARY KEY,
                ism          TEXT,
                lavozim      TEXT,
                kod          TEXT,
                filial       TEXT,
                telefon1     TEXT,
                telefon2     TEXT,
                tugilgan_kun TEXT,
                topic_id     INTEGER,
                status       TEXT DEFAULT 'pending',
                sana         TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS xabarlar (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                xodim_name  TEXT,
                filial      TEXT,
                xabar_turi  TEXT,
                vaqt        TEXT,
                holat       TEXT DEFAULT 'kutilmoqda',
                javob_vaqt  TEXT,
                msg_id      INTEGER
            )
        """)
        await db.commit()


# ── Xodim ────────────────────────────────────────────────────────
async def get_xodim(user_id: int) -> tuple | None:
    """Returns (status, topic_id, ism, lavozim, filial, kod)"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT status, topic_id, ism, lavozim, filial, kod FROM xodimlar WHERE user_id=?",
            (user_id,)
        ) as cur:
            return await cur.fetchone()


async def insert_xodim(user_id, ism, lavozim, kod, filial,
                       telefon1, telefon2, tugilgan_kun):
    sana = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO xodimlar
            (user_id, ism, lavozim, kod, filial, telefon1, telefon2,
             tugilgan_kun, topic_id, status, sana)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'pending', ?)
        """, (user_id, ism, lavozim, kod, filial,
              telefon1, telefon2, tugilgan_kun, sana))
        await db.commit()


async def approve_xodim(user_id: int, topic_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE xodimlar SET status='approved', topic_id=? WHERE user_id=?",
            (topic_id, user_id)
        )
        await db.commit()


async def reject_xodim(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM xodimlar WHERE user_id=?", (user_id,))
        await db.commit()


async def block_xodim(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE xodimlar SET status='blocked', topic_id=NULL WHERE user_id=?",
            (user_id,)
        )
        await db.commit()


async def unblock_xodim(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE xodimlar SET status='approved' WHERE user_id=?",
            (user_id,)
        )
        await db.commit()


async def reset_topic(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE xodimlar SET status='pending', topic_id=NULL WHERE user_id=?",
            (user_id,)
        )
        await db.commit()


async def delete_xodim(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM xodimlar WHERE user_id=?", (user_id,))
        await db.commit()


async def update_xodim_field(user_id: int, field: str, value: str):
    allowed = {"ism", "lavozim", "kod", "filial"}
    if field not in allowed:
        raise ValueError(f"Ruxsat etilmagan maydon: {field}")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE xodimlar SET {field}=? WHERE user_id=?",
            (value, user_id)
        )
        await db.commit()


async def search_xodimlar(query: str) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        if query.isdigit():
            async with db.execute(
                "SELECT ism, lavozim, filial, kod, user_id FROM xodimlar WHERE user_id=?",
                (int(query),)
            ) as cur:
                return await cur.fetchall()
        else:
            async with db.execute(
                "SELECT ism, lavozim, filial, kod, user_id FROM xodimlar WHERE ism LIKE ?",
                (f"%{query}%",)
            ) as cur:
                return await cur.fetchall()


async def get_approved_xodimlar() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT ism, lavozim, filial, kod, user_id FROM xodimlar WHERE status='approved'"
        ) as cur:
            return await cur.fetchall()


async def get_pending_xodimlar() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, ism, lavozim, kod, filial FROM xodimlar WHERE status='pending'"
        ) as cur:
            return await cur.fetchall()


async def get_blocked_xodimlar() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, ism, lavozim, filial, kod FROM xodimlar WHERE status='blocked'"
        ) as cur:
            return await cur.fetchall()


async def get_all_xodimlar_for_excel() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT user_id, ism, lavozim, kod, filial,
                   telefon1, telefon2, tugilgan_kun, status, sana
            FROM xodimlar
        """) as cur:
            return await cur.fetchall()


# ── Xabar ────────────────────────────────────────────────────────
async def insert_xabar(user_id, ism, filial, xabar_turi, msg_id) -> int:
    vaqt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO xabarlar (user_id, xodim_name, filial, xabar_turi, vaqt, holat, msg_id)
            VALUES (?, ?, ?, ?, ?, 'kutilmoqda', ?)
        """, (user_id, ism, filial, xabar_turi, vaqt, msg_id))
        await db.commit()
        return cur.lastrowid


async def get_xodim_by_topic(topic_id: int) -> tuple | None:
    """Returns (user_id, ism) for the employee who owns this topic."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, ism FROM xodimlar WHERE topic_id=? AND status='approved'",
            (topic_id,)
        ) as cur:
            return await cur.fetchone()


async def get_xabar(task_id: int) -> tuple | None:
    """Returns (user_id, xodim_name, msg_id, holat)"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, xodim_name, msg_id, holat FROM xabarlar WHERE id=?",
            (task_id,)
        ) as cur:
            return await cur.fetchone()


async def update_xabar_holat(task_id: int, holat: str):
    javob_vaqt = (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S") if holat == "bajarildi" else None
    )
    async with aiosqlite.connect(DB_PATH) as db:
        if javob_vaqt:
            await db.execute(
                "UPDATE xabarlar SET holat=?, javob_vaqt=? WHERE id=?",
                (holat, javob_vaqt, task_id)
            )
        else:
            await db.execute("UPDATE xabarlar SET holat=? WHERE id=?", (holat, task_id))
        await db.commit()


async def get_all_xabarlar_for_excel() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT id, user_id, xodim_name, filial,
                   xabar_turi, vaqt, holat, javob_vaqt
            FROM xabarlar
        """) as cur:
            return await cur.fetchall()


async def get_statistika() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(id), SUM(CASE WHEN holat='bajarildi' THEN 1 ELSE 0 END) FROM xabarlar"
        ) as cur:
            jami, bajarilgan = await cur.fetchone()
        async with db.execute(
            "SELECT vaqt, javob_vaqt FROM xabarlar WHERE holat='bajarildi'"
        ) as cur:
            times = await cur.fetchall()

    jami       = jami or 0
    bajarilgan = bajarilgan or 0
    total_min  = 0.0
    for t_kir, t_baj in times:
        try:
            d1 = datetime.strptime(t_kir, "%Y-%m-%d %H:%M:%S")
            d2 = datetime.strptime(t_baj, "%Y-%m-%d %H:%M:%S")
            total_min += (d2 - d1).total_seconds() / 60
        except Exception:
            continue
    ortacha = round(total_min / bajarilgan, 1) if bajarilgan > 0 else 0.0
    return {
        "jami":       jami,
        "bajarilgan": bajarilgan,
        "kutilmoqda": jami - bajarilgan,
        "ortacha":    ortacha,
    }
