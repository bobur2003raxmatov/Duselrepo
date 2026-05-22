import aiosqlite
from datetime import datetime
from config import DB_PATH, GROUP_TIMEOUT_SEC


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

        # Migration: group_fwd_id ustuni
        try:
            await db.execute("ALTER TABLE xabarlar ADD COLUMN group_fwd_id INTEGER")
            await db.commit()
        except Exception:
            pass

        # Migration: group_id ustuni
        try:
            await db.execute("ALTER TABLE xabarlar ADD COLUMN group_id INTEGER")
            await db.commit()
        except Exception:
            pass

        # Xabar guruhlari jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS xabar_guruhi (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                ism        TEXT,
                filial     TEXT,
                topic_id   INTEGER,
                holat      TEXT DEFAULT 'kutilmoqda',
                vaqt       TEXT,
                javob_vaqt TEXT
            )
        """)
        await db.commit()

        # FAQ jadvallari
        await db.execute("""
            CREATE TABLE IF NOT EXISTS faq_kategoriya (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                emoji  TEXT    DEFAULT '📌',
                nomi   TEXT,
                tartib INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS faq (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                kategoriya_id INTEGER,
                savol         TEXT,
                javob         TEXT,
                tartib        INTEGER DEFAULT 0
            )
        """)
        await db.commit()

        # Admin xabarlari → xodim shaxsiy chati mapping jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_msg_map (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER,
                group_msg_id   INTEGER,
                private_msg_id INTEGER
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


async def get_xodim_full(user_id: int) -> tuple | None:
    """Barcha maydonlar: (user_id, ism, lavozim, kod, filial, tel1, tel2, tug_kun, topic_id, status, sana)"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT user_id, ism, lavozim, kod, filial,
                   telefon1, telefon2, tugilgan_kun, topic_id, status, sana
            FROM xodimlar WHERE user_id=?
        """, (user_id,)) as cur:
            return await cur.fetchone()


async def search_xodimlar(query: str) -> list:
    """Returns (ism, lavozim, filial, kod, user_id, status)"""
    async with aiosqlite.connect(DB_PATH) as db:
        if query.isdigit():
            async with db.execute(
                "SELECT ism, lavozim, filial, kod, user_id, status FROM xodimlar WHERE user_id=?",
                (int(query),)
            ) as cur:
                return await cur.fetchall()
        else:
            async with db.execute(
                "SELECT ism, lavozim, filial, kod, user_id, status FROM xodimlar WHERE ism LIKE ?",
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


# ── Xabar guruhi ────────────────────────────────────────────────
async def create_xabar_guruhi(user_id: int, ism: str, filial: str, topic_id: int) -> int:
    vaqt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO xabar_guruhi (user_id, ism, filial, topic_id, holat, vaqt) VALUES (?, ?, ?, ?, 'kutilmoqda', ?)",
            (user_id, ism, filial, topic_id, vaqt)
        )
        await db.commit()
        return cur.lastrowid


async def get_active_group(user_id: int) -> tuple | None:
    """Oxirgi GROUP_TIMEOUT_SEC soniya ichida ochiq guruh bo'lsa (group_id, topic_id) qaytaradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(f"""
            SELECT g.id, g.topic_id
            FROM xabar_guruhi g
            WHERE g.user_id = ? AND g.holat = 'kutilmoqda'
            AND (
                SELECT MAX(x.vaqt) FROM xabarlar x WHERE x.group_id = g.id
            ) >= datetime('now', 'localtime', '-{GROUP_TIMEOUT_SEC} seconds')
            ORDER BY g.id DESC LIMIT 1
        """, (user_id,)) as cur:
            return await cur.fetchone()


async def get_group_info(group_id: int) -> tuple | None:
    """Returns (user_id, ism, filial, topic_id, holat)"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, ism, filial, topic_id, holat FROM xabar_guruhi WHERE id=?",
            (group_id,)
        ) as cur:
            return await cur.fetchone()


async def update_group_holat(group_id: int, holat: str):
    javob_vaqt = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if holat == "bajarildi" else None
    async with aiosqlite.connect(DB_PATH) as db:
        if javob_vaqt:
            await db.execute(
                "UPDATE xabar_guruhi SET holat=?, javob_vaqt=? WHERE id=?",
                (holat, javob_vaqt, group_id)
            )
            await db.execute(
                "UPDATE xabarlar SET holat=?, javob_vaqt=? WHERE group_id=?",
                (holat, javob_vaqt, group_id)
            )
        else:
            await db.execute("UPDATE xabar_guruhi SET holat=? WHERE id=?", (holat, group_id))
            await db.execute("UPDATE xabarlar SET holat=? WHERE group_id=?", (holat, group_id))
        await db.commit()


async def get_most_important_msg(group_id: int) -> tuple | None:
    """Guruhdan eng muhim xabarni qaytaradi: rasm > video > fayl > ovoz > matn."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
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
            FROM xabarlar WHERE group_id = ?
            ORDER BY priority ASC, id DESC
            LIMIT 1
        """, (group_id,)) as cur:
            return await cur.fetchone()


async def count_group_msgs(group_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM xabarlar WHERE group_id=?", (group_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


# ── Xabar ────────────────────────────────────────────────────────
async def insert_xabar(user_id, ism, filial, xabar_turi, msg_id, group_id=None) -> int:
    vaqt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO xabarlar (user_id, xodim_name, filial, xabar_turi, vaqt, holat, msg_id, group_id)
            VALUES (?, ?, ?, ?, ?, 'kutilmoqda', ?, ?)
        """, (user_id, ism, filial, xabar_turi, vaqt, msg_id, group_id))
        await db.commit()
        return cur.lastrowid


async def update_xabar_group_fwd_id(task_id: int, group_fwd_id: int):
    """Guruhga forward qilingan xabar ID sini saqlaydi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE xabarlar SET group_fwd_id=? WHERE id=?",
            (group_fwd_id, task_id)
        )
        await db.commit()


async def get_xabar_by_group_fwd_id(group_fwd_id: int) -> tuple | None:
    """Guruh forward ID si bo'yicha (user_id, msg_id) qaytaradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, msg_id FROM xabarlar WHERE group_fwd_id=?",
            (group_fwd_id,)
        ) as cur:
            return await cur.fetchone()


async def insert_admin_msg_map(user_id: int, group_msg_id: int, private_msg_id: int):
    """Admin xabari → xodim shaxsiy chati mapping ni saqlaydi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO admin_msg_map (user_id, group_msg_id, private_msg_id) VALUES (?, ?, ?)",
            (user_id, group_msg_id, private_msg_id)
        )
        await db.commit()


async def get_group_msg_id_by_private(user_id: int, private_msg_id: int) -> int | None:
    """Xodim shaxsiy chatidagi xabar ID si bo'yicha guruh xabar ID sini qaytaradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT group_msg_id FROM admin_msg_map WHERE user_id=? AND private_msg_id=?",
            (user_id, private_msg_id)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


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


async def get_kunlik_statistika() -> list:
    """Har bir xodim uchun bugungi guruh / bajarilgan soni."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT ism, filial,
                   COUNT(*) AS jami,
                   SUM(CASE WHEN holat='bajarildi' THEN 1 ELSE 0 END) AS bajarildi
            FROM xabar_guruhi
            WHERE date(vaqt) = date('now', 'localtime')
            GROUP BY user_id
            ORDER BY jami DESC
        """) as cur:
            return await cur.fetchall()


async def get_statistika() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        # Yangi tizim: guruhlar
        async with db.execute(
            "SELECT COUNT(*), SUM(CASE WHEN holat='bajarildi' THEN 1 ELSE 0 END) FROM xabar_guruhi"
        ) as cur:
            g_jami, g_baj = await cur.fetchone()

        # Eski tizim: guruhsiz xabarlar
        async with db.execute(
            "SELECT COUNT(*), SUM(CASE WHEN holat='bajarildi' THEN 1 ELSE 0 END) FROM xabarlar WHERE group_id IS NULL"
        ) as cur:
            m_jami, m_baj = await cur.fetchone()

        # O'rtacha vaqt (guruhlar + eski xabarlar)
        async with db.execute("""
            SELECT vaqt, javob_vaqt FROM xabar_guruhi WHERE holat='bajarildi'
            UNION ALL
            SELECT vaqt, javob_vaqt FROM xabarlar WHERE holat='bajarildi' AND group_id IS NULL
        """) as cur:
            times = await cur.fetchall()

    jami       = (g_jami or 0) + (m_jami or 0)
    bajarilgan = (g_baj or 0) + (m_baj or 0)
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


# ── FAQ ──────────────────────────────────────────────────────────
async def get_faq_kategoriyalar() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, emoji, nomi FROM faq_kategoriya ORDER BY tartib, id"
        ) as cur:
            return await cur.fetchall()


async def get_faq_savollar(kategoriya_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, savol FROM faq WHERE kategoriya_id=? ORDER BY tartib, id",
            (kategoriya_id,)
        ) as cur:
            return await cur.fetchall()


async def get_faq_item(faq_id: int) -> tuple | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT savol, javob, kategoriya_id FROM faq WHERE id=?",
            (faq_id,)
        ) as cur:
            return await cur.fetchone()


async def add_faq_kategoriya(emoji: str, nomi: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO faq_kategoriya (emoji, nomi) VALUES (?, ?)",
            (emoji, nomi)
        )
        await db.commit()
        return cur.lastrowid


async def add_faq(kategoriya_id: int, savol: str, javob: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO faq (kategoriya_id, savol, javob) VALUES (?, ?, ?)",
            (kategoriya_id, savol, javob)
        )
        await db.commit()
        return cur.lastrowid


async def delete_faq(faq_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM faq WHERE id=?", (faq_id,))
        await db.commit()


async def delete_faq_kategoriya(kategoriya_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM faq WHERE kategoriya_id=?", (kategoriya_id,))
        await db.execute("DELETE FROM faq_kategoriya WHERE id=?", (kategoriya_id,))
        await db.commit()
