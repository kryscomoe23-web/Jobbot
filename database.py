import sqlite3
import os

DB_PATH = "/tmp/jobbot.db"


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_tables(conn)
    return conn


def init_tables(conn):
    conn.executescript("""
        DROP TABLE IF EXISTS offers;
        DROP TABLE IF EXISTS logs;

        CREATE TABLE offers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            company     TEXT NOT NULL,
            site        TEXT NOT NULL,
            track       TEXT DEFAULT 'a',
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

        CREATE TABLE logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            message    TEXT,
            level      TEXT DEFAULT 'info',
            created_at TEXT
        );
    """)
    conn.commit()


def init_db():
    db = get_db()
    db.close()
