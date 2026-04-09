import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobbot.db")


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS offers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            company     TEXT NOT NULL,
            site        TEXT NOT NULL,
            location    TEXT,
            salary      TEXT,
            url         TEXT UNIQUE,
            score       INTEGER,
            ai_analysis TEXT,
            lm_draft    TEXT,
            lm_final    TEXT,
            status      TEXT DEFAULT 'pending',
            created_at  TEXT,
            sent_at     TEXT
        );
        CREATE TABLE IF NOT EXISTS logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            message    TEXT,
            level      TEXT DEFAULT 'info',
            created_at TEXT
        );
    """)
    db.commit()
    db.close()
