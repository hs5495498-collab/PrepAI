"""SQLite connection and schema management, kept separate from storage.py's
repository functions and from the API route handlers in main.py.

The schema is created with CREATE TABLE/INDEX IF NOT EXISTS, so opening a
connection against an existing database file never drops or recreates
anything - it only fills in tables that are missing.
"""
import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "prepai.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS interviews (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    category TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    question_count INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('in_progress', 'completed')),
    question_source TEXT NOT NULL CHECK (question_source IN ('fixed', 'ai')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    user_id INTEGER
);

CREATE TABLE IF NOT EXISTS questions (
    interview_id TEXT NOT NULL REFERENCES interviews (id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    text TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (interview_id, id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_questions_position ON questions (interview_id, position);

CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    UNIQUE (interview_id, question_id),
    FOREIGN KEY (interview_id, question_id) REFERENCES questions (interview_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_interviews_user_id ON interviews (user_id);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    csrf_token TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id);

CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    total_score INTEGER NOT NULL CHECK (total_score >= 0 AND total_score <= 100),
    relevance_score INTEGER NOT NULL CHECK (relevance_score >= 0 AND relevance_score <= 30),
    correctness_score INTEGER NOT NULL CHECK (correctness_score >= 0 AND correctness_score <= 35),
    completeness_score INTEGER NOT NULL CHECK (completeness_score >= 0 AND completeness_score <= 25),
    clarity_score INTEGER NOT NULL CHECK (clarity_score >= 0 AND clarity_score <= 10),
    relevance_assessment TEXT NOT NULL,
    correctness_assessment TEXT NOT NULL,
    explanation TEXT NOT NULL,
    strengths TEXT NOT NULL,
    weaknesses TEXT NOT NULL,
    suggestions TEXT NOT NULL,
    example_answer TEXT,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (interview_id, question_id),
    FOREIGN KEY (interview_id, question_id) REFERENCES questions (interview_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_evaluations_interview ON evaluations (interview_id);
"""


def get_db_path() -> Path:
    configured = os.environ.get("DATABASE_PATH")
    return Path(configured) if configured else DEFAULT_DB_PATH


def connect() -> sqlite3.Connection:
    """Opens a fresh connection to whatever DATABASE_PATH currently points
    to, enables foreign-key enforcement (off by default in SQLite), and
    makes sure the schema exists. Callers are responsible for closing the
    connection they get back."""
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA)
    return conn
