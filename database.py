import aiosqlite
from contextlib import asynccontextmanager
from datetime import datetime
from config import DB_PATH, GROUP_TIMEOUT_SEC, ADMIN_ID

# ── Ulanish yordamchisi ──────────────────────────────────────────
# Hozir har so'rovda yangi SQLite ulanish ochiladi va yopiladi.
# Bu kichik Telegram botlar uchun yetarli. Kelajakda PostgreSQL ga
# o'tganda shu get_db() ni connection pool bilan almashtirish kifoya.
@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        yield conn


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

        # Baholash (reyting) jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS baholash (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id   INTEGER UNIQUE,
                checker_id INTEGER,
                agent_id   INTEGER,
                yulduz     INTEGER,
                vaqt       TEXT
            )
        """)
        await db.commit()

        # Checker faollik vaqti
        await db.execute("""
            CREATE TABLE IF NOT EXISTS checker_faollik (
                checker_id  INTEGER PRIMARY KEY,
                last_active TEXT
            )
        """)
        await db.commit()

        # urgency ustuni xabar_guruhi uchun
        try:
            await db.execute("ALTER TABLE xabar_guruhi ADD COLUMN urgency TEXT DEFAULT 'oddiy'")
            await db.commit()
        except Exception:
            pass

        # Agent → Checker biriktirish jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS biriktirish (
                agent_id   INTEGER PRIMARY KEY,
                checker_id INTEGER
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

        # Klientlar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS klientlar (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                rasm_file_id      TEXT,
                firma_nomi        TEXT NOT NULL,
                telefon1          TEXT NOT NULL,
                telefon2          TEXT,
                inn               TEXT UNIQUE,
                orienter          TEXT NOT NULL,
                lokatsiya_lat     REAL,
                lokatsiya_lon     REAL,
                kategoriya        TEXT NOT NULL,
                dokon_turi        TEXT NOT NULL,
                distributor       TEXT NOT NULL,
                agent_kod         TEXT NOT NULL,
                vizit_kun         TEXT NOT NULL,
                chastota          TEXT NOT NULL,
                limit_summa       REAL NOT NULL,
                brendlar          TEXT,
                status            TEXT DEFAULT 'pending',
                reject_reason     TEXT,
                sana              TEXT,
                supervisor_id     INTEGER NOT NULL,
                lokatsiya_address TEXT
            )
        """)
        await db.commit()

        # Migration: lokatsiya_address ustuni (eski DB lar uchun)
        try:
            await db.execute("ALTER TABLE klientlar ADD COLUMN lokatsiya_address TEXT")
            await db.commit()
        except Exception:
            pass

        # Sorovlar (agent requests) table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sorovlar (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id      INTEGER NOT NULL,
                agent_ism     TEXT    NOT NULL,
                tur           TEXT    NOT NULL,
                dokon_nomi    TEXT,
                yangi_qiymat  TEXT,
                lat           REAL,
                lon           REAL,
                foto_ids      TEXT,
                izoh          TEXT,
                status        TEXT    DEFAULT 'pending_supervisor',
                supervisor_id INTEGER,
                sup_msg_id    INTEGER,
                admin_msg_id  INTEGER,
                sana          TEXT    NOT NULL
            )
        """)
        await db.commit()

        # Migration: group_id for sorovlar (which group the approved request was posted to)
        try:
            await db.execute("ALTER TABLE sorovlar ADD COLUMN group_id INTEGER")
            await db.commit()
        except Exception:
            pass

        # Supervisor → Telegram group mapping
        await db.execute("""
            CREATE TABLE IF NOT EXISTS supervisor_group (
                supervisor_id INTEGER PRIMARY KEY,
                group_chat_id INTEGER NOT NULL
            )
        """)

        # DB versiyasi — migratsiya nazorati uchun
        await db.execute("""
            CREATE TABLE IF NOT EXISTS db_version (
                version INTEGER NOT NULL DEFAULT 0
            )
        """)
        async with db.execute("SELECT COUNT(*) FROM db_version") as cur:
            count = (await cur.fetchone())[0]
        if count == 0:
            await db.execute("INSERT INTO db_version VALUES (1)")

        # Adminlar jadvali — bir nechta admin qo'shish imkoni
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """)
        # Asosiy admin har doim jadvalda bo'lishi kerak
        await db.execute(
            "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (ADMIN_ID,)
        )

        await db.commit()

        # Audit log jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     BIGINT,
                user_role   VARCHAR(50),
                action_type VARCHAR(100),
                target      TEXT,
                old_value   TEXT,
                new_value   TEXT,
                status      VARCHAR(50),
                request_id  INTEGER,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

        # Migration: inn ustunidan NOT NULL ni olib tashlash
        # (klient_inn handler ixtiyoriy deb yozadi, lekin eski DB NOT NULL bilan yaratilgan)
        try:
            async with db.execute("PRAGMA table_info(klientlar)") as cur:
                cols = await cur.fetchall()
            inn_row = next((c for c in cols if c[1] == "inn"), None)
            if inn_row and inn_row[3] == 1:  # notnull flag
                await db.execute("BEGIN")
                await db.execute("ALTER TABLE klientlar RENAME TO klientlar_old")
                await db.execute("""
                    CREATE TABLE klientlar (
                        id                INTEGER PRIMARY KEY AUTOINCREMENT,
                        rasm_file_id      TEXT,
                        firma_nomi        TEXT NOT NULL,
                        telefon1          TEXT NOT NULL,
                        telefon2          TEXT,
                        inn               TEXT UNIQUE,
                        orienter          TEXT NOT NULL,
                        lokatsiya_lat     REAL,
                        lokatsiya_lon     REAL,
                        kategoriya        TEXT NOT NULL,
                        dokon_turi        TEXT NOT NULL,
                        distributor       TEXT NOT NULL,
                        agent_kod         TEXT NOT NULL,
                        vizit_kun         TEXT NOT NULL,
                        chastota          TEXT NOT NULL,
                        limit_summa       REAL NOT NULL,
                        brendlar          TEXT,
                        status            TEXT DEFAULT 'pending',
                        reject_reason     TEXT,
                        sana              TEXT,
                        supervisor_id     INTEGER NOT NULL,
                        lokatsiya_address TEXT
                    )
                """)
                await db.execute("""
                    INSERT INTO klientlar
                    SELECT id, rasm_file_id, firma_nomi, telefon1, telefon2, inn, orienter,
                           lokatsiya_lat, lokatsiya_lon, kategoriya, dokon_turi, distributor,
                           agent_kod, vizit_kun, chastota, limit_summa, brendlar, status,
                           reject_reason, sana, supervisor_id, lokatsiya_address
                    FROM klientlar_old
                """)
                await db.execute("DROP TABLE klientlar_old")
                await db.commit()
        except Exception:
            try:
                await db.execute("ROLLBACK")
            except Exception:
                pass


# ── DB versiyasi ─────────────────────────────────────────────────
async def get_db_version() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT version FROM db_version LIMIT 1") as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def set_db_version(version: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM db_version")
        await db.execute("INSERT INTO db_version VALUES (?)", (version,))
        await db.commit()


# ── Adminlar ─────────────────────────────────────────────────────
async def get_admins() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM admins") as cur:
            return [r[0] for r in await cur.fetchall()]


async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM admins WHERE user_id=?", (user_id,)
        ) as cur:
            return await cur.fetchone() is not None


async def add_admin(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,)
        )
        await db.commit()


async def remove_admin(user_id: int) -> None:
    if user_id == ADMIN_ID:
        return  # Asosiy adminni o'chirib bo'lmaydi
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
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


# ── Biriktirish ──────────────────────────────────────────────────
async def get_biriktirish(agent_id: int) -> int | None:
    """Agent uchun biriktirilgan checker_id ni qaytaradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT checker_id FROM biriktirish WHERE agent_id=?", (agent_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def set_biriktirish(agent_id: int, checker_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO biriktirish (agent_id, checker_id) VALUES (?, ?)",
            (agent_id, checker_id)
        )
        await db.commit()


async def delete_biriktirish(agent_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM biriktirish WHERE agent_id=?", (agent_id,))
        await db.commit()


async def get_all_biriktirish() -> list:
    """Returns [(agent_id, agent_ism, checker_id, checker_ism)]"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT b.agent_id, a.ism, b.checker_id, c.ism
            FROM biriktirish b
            LEFT JOIN xodimlar a ON a.user_id = b.agent_id
            LEFT JOIN xodimlar c ON c.user_id = b.checker_id
        """) as cur:
            return await cur.fetchall()


async def get_agents() -> list:
    """Barcha tasdiqlangan agentlar."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT ism, lavozim, filial, kod, user_id, status FROM xodimlar WHERE lavozim='Agent' AND status='approved'"
        ) as cur:
            return await cur.fetchall()


async def get_available_checkers() -> list:
    """Supervisor, Filial Rahbari, Distribyutor — tasdiqlangan."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT ism, lavozim, filial, kod, user_id, status FROM xodimlar
            WHERE lavozim IN ('Supervisor', 'Filial Rahbari', 'Distribyutor')
            AND status = 'approved'
        """) as cur:
            return await cur.fetchall()


async def get_distributors() -> list:
    """Barcha tasdiqlangan distribyutorlar."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT ism, lavozim, filial, kod, user_id, status FROM xodimlar
            WHERE lavozim = 'Distribyutor'
            AND status = 'approved'
        """) as cur:
            return await cur.fetchall()


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


async def get_group_msgs_list(group_id: int) -> list:
    """Returns [(xabar_turi, vaqt), ...] for all messages in a group, oldest first."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT xabar_turi, vaqt FROM xabarlar WHERE group_id=? ORDER BY id ASC",
            (group_id,)
        ) as cur:
            return await cur.fetchall()


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


# ── Urgency ──────────────────────────────────────────────────────
async def set_urgency(group_id: int, urgency: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE xabar_guruhi SET urgency=? WHERE id=?", (urgency, group_id)
        )
        await db.commit()


async def get_group_urgency(group_id: int) -> str | None:
    """Guruhning urgency darajasini qaytaradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT urgency FROM xabar_guruhi WHERE id=?", (group_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


# ── Baholash (reyting) ───────────────────────────────────────────
async def add_baholash(group_id: int, checker_id: int, agent_id: int, yulduz: int):
    vaqt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO baholash (group_id, checker_id, agent_id, yulduz, vaqt) VALUES (?,?,?,?,?)",
            (group_id, checker_id, agent_id, yulduz, vaqt)
        )
        await db.commit()


async def get_agent_rating_summary(agent_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT ROUND(AVG(yulduz),1), COUNT(*) FROM baholash WHERE agent_id=?",
            (agent_id,)
        ) as cur:
            avg, total = await cur.fetchone()
        async with db.execute(
            "SELECT ROUND(AVG(yulduz),1) FROM baholash WHERE agent_id=? AND date(vaqt)>=date('now','-7 days','localtime')",
            (agent_id,)
        ) as cur:
            haftalik = (await cur.fetchone())[0]
    return {"avg": avg or 0.0, "total": total or 0, "haftalik": haftalik or 0.0}


async def get_agent_leaderboard() -> list:
    """[(user_id, ism, filial, avg, total, haftalik_avg)]"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT x.user_id, x.ism, x.filial,
                   ROUND(AVG(b.yulduz),1) as avg_r,
                   COUNT(b.id) as total,
                   ROUND(AVG(CASE WHEN date(b.vaqt) >= date('now','-7 days','localtime') THEN b.yulduz END),1) as haftalik
            FROM xodimlar x
            JOIN baholash b ON b.agent_id = x.user_id
            WHERE x.lavozim='Agent' AND x.status='approved'
            GROUP BY x.user_id
            ORDER BY avg_r DESC, total DESC
        """) as cur:
            return await cur.fetchall()


# ── Checker faollik ──────────────────────────────────────────────
async def update_checker_faollik(checker_id: int):
    vaqt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO checker_faollik (checker_id, last_active) VALUES (?,?)",
            (checker_id, vaqt)
        )
        await db.commit()


async def get_checker_faollik(checker_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT last_active FROM checker_faollik WHERE checker_id=?", (checker_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


# ── Haftalik hisobot ─────────────────────────────────────────────
async def get_checker_weekly_stats() -> list:
    """[(checker_ism, agent_count, topshiriq, bajarildi, avg_reyting)]"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
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
        """) as cur:
            return await cur.fetchall()


# ── Agent faollik tekshiruvi ─────────────────────────────────────
async def get_agents_without_messages_today() -> list:
    """Bugun hech qanday xabar yubormaganlar: [(user_id, ism)]"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT x.user_id, x.ism FROM xodimlar x
            WHERE x.lavozim='Agent' AND x.status='approved'
            AND x.user_id NOT IN (
                SELECT DISTINCT user_id FROM xabar_guruhi
                WHERE date(vaqt) = date('now','localtime')
            )
        """) as cur:
            return await cur.fetchall()


# ── Filial statistikasi ──────────────────────────────────────────
async def get_filial_stats(period: str = "haftalik") -> list:
    """[(filial, agent_soni, topshiriq, bajarildi, avg_reyting, avg_vaqt_daqiqa)]"""
    period_filter = {
        "haftalik": "date('now','-7 days','localtime')",
        "oylik":    "date('now','-30 days','localtime')",
        "yillik":   "date('now','-365 days','localtime')",
        "hammasi":  "date('2000-01-01')",
    }.get(period, "date('now','-7 days','localtime')")

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(f"""
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
        """) as cur:
            return await cur.fetchall()


async def get_agent_today_stats(agent_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COUNT(*), SUM(CASE WHEN holat='bajarildi' THEN 1 ELSE 0 END)
            FROM xabar_guruhi
            WHERE user_id=? AND date(vaqt)=date('now','localtime')
        """, (agent_id,)) as cur:
            bugun, bajarildi = await cur.fetchone()
    return {"bugun": bugun or 0, "bajarildi": bajarildi or 0}


async def get_unassigned_agents() -> list:
    """Checker biriktirilmagan approved agentlar: [(ism, user_id, filial, kod)]"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT x.ism, x.user_id, x.filial, x.kod
            FROM xodimlar x
            WHERE x.lavozim='Agent' AND x.status='approved'
            AND x.user_id NOT IN (SELECT agent_id FROM biriktirish)
        """) as cur:
            return await cur.fetchall()


async def get_latest_group_fwd_id(group_id: int) -> int | None:
    """Guruh uchun oxirgi forward qilingan xabar ID sini qaytaradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT group_fwd_id FROM xabarlar WHERE group_id=? AND group_fwd_id IS NOT NULL ORDER BY id DESC LIMIT 1",
            (group_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def get_all_biriktirish_detailed() -> list:
    """[(agent_id, agent_ism, checker_id, checker_ism, agent_filial, agent_status)]"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT b.agent_id, a.ism, b.checker_id, c.ism, a.filial, a.status
            FROM biriktirish b
            JOIN xodimlar a ON a.user_id = b.agent_id
            LEFT JOIN xodimlar c ON c.user_id = b.checker_id
            ORDER BY a.ism
        """) as cur:
            return await cur.fetchall()


# ── Klientlar (Clients) ──────────────────────────────────────────
async def insert_klient(rasm_file_id, firma_nomi, telefon1, telefon2, inn, orienter,
                       lokatsiya_lat, lokatsiya_lon, lokatsiya_address, kategoriya, dokon_turi, distributor,
                       agent_kod, vizit_kun, chastota, limit_summa, brendlar, supervisor_id) -> int:
    """Yangi klientni qo'shadi."""
    sana = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO klientlar (rasm_file_id, firma_nomi, telefon1, telefon2, inn, orienter,
                                  lokatsiya_lat, lokatsiya_lon, lokatsiya_address, kategoriya, dokon_turi,
                                  distributor, agent_kod, vizit_kun, chastota, limit_summa,
                                  brendlar, status, sana, supervisor_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """, (rasm_file_id, firma_nomi, telefon1, telefon2, inn, orienter,
              lokatsiya_lat, lokatsiya_lon, lokatsiya_address, kategoriya, dokon_turi,
              distributor, agent_kod, vizit_kun, chastota, limit_summa,
              brendlar, sana, supervisor_id))
        await db.commit()
        return cur.lastrowid


async def get_klient(klient_id: int) -> tuple | None:
    """Full klient info."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM klientlar WHERE id=?", (klient_id,)
        ) as cur:
            return await cur.fetchone()


async def get_klientlar_by_supervisor(supervisor_id: int) -> list:
    """Supervisorning barcha klientlari."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM klientlar WHERE supervisor_id=? ORDER BY sana DESC",
            (supervisor_id,)
        ) as cur:
            return await cur.fetchall()


async def get_all_klientlar(status: str | None = None) -> list:
    """Barcha klientlar (admin uchun)."""
    async with aiosqlite.connect(DB_PATH) as db:
        if status:
            async with db.execute(
                "SELECT * FROM klientlar WHERE status=? ORDER BY sana DESC", (status,)
            ) as cur:
                return await cur.fetchall()
        else:
            async with db.execute(
                "SELECT * FROM klientlar ORDER BY sana DESC"
            ) as cur:
                return await cur.fetchall()


async def approve_klient(klient_id: int):
    """Klientni tasdiqlash."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE klientlar SET status='approved' WHERE id=?", (klient_id,)
        )
        await db.commit()


async def reject_klient(klient_id: int, reason: str):
    """Klientni rad etish."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE klientlar SET status='rejected', reject_reason=? WHERE id=?",
            (reason, klient_id)
        )
        await db.commit()


async def search_klientlar(query: str) -> list:
    """Klientlarni qidirish (firma_nomi, inn, distributor, telefon bo'yicha)."""
    # Normalize to last-9-digit national number for phone matching
    digits = "".join(filter(str.isdigit, query))
    if len(digits) == 12 and digits.startswith("998"):
        phone_q = digits[3:]
    elif len(digits) == 10 and digits.startswith("0"):
        phone_q = digits[1:]
    elif len(digits) >= 9:
        phone_q = digits[-9:]
    else:
        phone_q = digits

    async with aiosqlite.connect(DB_PATH) as db:
        # Strip '+' and spaces from stored phone before comparing
        async with db.execute("""
            SELECT * FROM klientlar
            WHERE firma_nomi LIKE ?
               OR inn LIKE ?
               OR distributor LIKE ?
               OR REPLACE(REPLACE(telefon1, '+', ''), ' ', '') LIKE ?
               OR REPLACE(REPLACE(telefon2, '+', ''), ' ', '') LIKE ?
            ORDER BY sana DESC
        """, (f"%{query}%", f"%{query}%", f"%{query}%",
              f"%{phone_q}%", f"%{phone_q}%")) as cur:
            return await cur.fetchall()


async def get_all_klientlar_for_excel() -> list:
    """Excel export uchun barcha klientlar."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM klientlar WHERE status='approved' ORDER BY firma_nomi"
        ) as cur:
            return await cur.fetchall()


async def get_klientlar_stats() -> dict:
    """Klientlar soni statuslar bo'yicha."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT status, COUNT(*) FROM klientlar GROUP BY status"
        ) as cur:
            rows = await cur.fetchall()
    stats = {"pending": 0, "approved": 0, "rejected": 0}
    for status, count in rows:
        if status in stats:
            stats[status] = count
    stats["total"] = sum(stats.values())
    return stats


async def get_opened_klientlar_for_excel() -> list:
    """Ochilgan (pending + approved) klientlar Excel uchun."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id, firma_nomi, telefon1, telefon2, inn, orienter,
                      lokatsiya_lat, lokatsiya_lon, lokatsiya_address,
                      kategoriya, dokon_turi, distributor, agent_kod,
                      limit_summa, brendlar, status, sana, supervisor_id
               FROM klientlar
               WHERE status IN ('pending', 'approved')
               ORDER BY sana DESC"""
        ) as cur:
            return await cur.fetchall()


# ── Sorovlar (agent requests) ─────────────────────────────────────

async def insert_sorov(agent_id: int, agent_ism: str, tur: str,
                       dokon_nomi: str | None, yangi_qiymat: str | None,
                       lat: float | None, lon: float | None,
                       foto_ids: str | None, izoh: str | None,
                       supervisor_id: int | None) -> int:
    sana = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO sorovlar
               (agent_id, agent_ism, tur, dokon_nomi, yangi_qiymat,
                lat, lon, foto_ids, izoh, status, supervisor_id, sana)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (agent_id, agent_ism, tur, dokon_nomi, yangi_qiymat,
             lat, lon, foto_ids, izoh,
             "pending_supervisor" if supervisor_id else "pending_admin",
             supervisor_id, sana),
        )
        await db.commit()
        return cur.lastrowid


async def get_sorov(sorov_id: int) -> tuple | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM sorovlar WHERE id=?", (sorov_id,)
        ) as cur:
            return await cur.fetchone()


async def update_sorov_status(sorov_id: int, status: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sorovlar SET status=? WHERE id=?", (status, sorov_id)
        )
        await db.commit()


async def update_sorov_sup_msg_id(sorov_id: int, msg_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sorovlar SET sup_msg_id=? WHERE id=?", (msg_id, sorov_id)
        )
        await db.commit()


async def update_sorov_admin_msg_id(sorov_id: int, msg_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sorovlar SET admin_msg_id=? WHERE id=?", (msg_id, sorov_id)
        )
        await db.commit()


async def get_sorov_by_sup_msg_id(msg_id: int) -> tuple | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM sorovlar WHERE sup_msg_id=?", (msg_id,)
        ) as cur:
            return await cur.fetchone()


async def get_sorov_by_admin_msg_id(msg_id: int) -> tuple | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM sorovlar WHERE admin_msg_id=?", (msg_id,)
        ) as cur:
            return await cur.fetchone()


async def update_sorov_group_id(sorov_id: int, group_chat_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sorovlar SET group_id=? WHERE id=?", (group_chat_id, sorov_id)
        )
        await db.commit()


# ── Supervisor ↔ Group mapping ────────────────────────────────────

async def set_supervisor_group(supervisor_id: int, group_chat_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO supervisor_group (supervisor_id, group_chat_id) VALUES (?, ?)",
            (supervisor_id, group_chat_id)
        )
        await db.commit()


async def get_supervisor_group(supervisor_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT group_chat_id FROM supervisor_group WHERE supervisor_id=?",
            (supervisor_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def delete_supervisor_group(supervisor_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM supervisor_group WHERE supervisor_id=?", (supervisor_id,))
        await db.commit()


async def check_duplicate_firma(firma_nomi: str) -> dict | None:
    """Firma nomi bo'yicha dublikat tekshirish."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM klientlar WHERE LOWER(firma_nomi) = LOWER(?) LIMIT 1",
            (firma_nomi,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                cols = ("id", "rasm", "firma_nomi", "telefon1", "telefon2", "inn", "orienter",
                        "lat", "lon", "kategoriya", "dokon_turi", "distributor", "agent_kod",
                        "vizit_kun", "chastota", "limit", "brendlar", "status", "reason", "sana", "sup_id",
                        "lokatsiya_address")
                return dict(zip(cols, row))
            return None


# ── Audit log ────────────────────────────────────────────────────

async def insert_audit_log(user_id: int, user_role: str, action_type: str,
                            target: str | None = None, old_value: str | None = None,
                            new_value: str | None = None, status: str | None = None,
                            request_id: int | None = None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO audit_log
              (user_id, user_role, action_type, target, old_value, new_value, status, request_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, user_role, action_type, target, old_value, new_value, status, request_id))
        await db.commit()


async def get_audit_logs(filter_type: str = "all", limit: int = 20) -> list:
    """Returns [(id, user_id, user_role, action_type, target, old_value, new_value, status, request_id, created_at, ism)]"""
    if filter_type == "agent":
        where = "WHERE a.user_role = 'agent'"
    elif filter_type == "supervisor":
        where = "WHERE a.user_role IN ('supervisor', 'filial_rahbari')"
    elif filter_type == "rejected":
        where = "WHERE a.status = 'rejected'"
    else:
        where = ""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(f"""
            SELECT a.id, a.user_id, a.user_role, a.action_type, a.target,
                   a.old_value, a.new_value, a.status, a.request_id, a.created_at,
                   x.ism
            FROM audit_log a
            LEFT JOIN xodimlar x ON x.user_id = a.user_id
            {where}
            ORDER BY a.id DESC LIMIT ?
        """, (limit,)) as cur:
            return await cur.fetchall()


async def check_duplicate_telefon(telefon: str) -> dict | None:
    """Telefon raqami bo'yicha dublikat tekshirish."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM klientlar WHERE telefon1 = ? OR telefon2 = ? LIMIT 1",
            (telefon, telefon)
        ) as cur:
            row = await cur.fetchone()
            if row:
                cols = ("id", "rasm", "firma_nomi", "telefon1", "telefon2", "inn", "orienter",
                        "lat", "lon", "kategoriya", "dokon_turi", "distributor", "agent_kod",
                        "vizit_kun", "chastota", "limit", "brendlar", "status", "reason", "sana", "sup_id",
                        "lokatsiya_address")
                return dict(zip(cols, row))
            return None
