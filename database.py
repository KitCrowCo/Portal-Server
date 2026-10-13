# backend/database.py
import os
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "")

connect_args = {}
if not DATABASE_URL or "sqlite" in DATABASE_URL:
    db_path = "./data/server.db"
    db_dir = os.path.dirname(db_path)
    if not os.path.exists(db_dir): os.makedirs(db_dir)
    DATABASE_URL = f"sqlite:///{db_path}"
    connect_args = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgres://"):
    # Handle "postgres://" vs "postgresql://" for Heroku/various providers
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_size=20, max_overflow=40, pool_timeout=60)
    
# ── SQLite WAL mode ──
# WAL (Write-Ahead Logging) allows concurrent reads during writes — important when multiple users may be saving state simultaneously.
# synchronous is intentionally left at its default (FULL under WAL mode).
# FULL ensures every committed transaction is flushed to disk before returning.
# This is correct for financial ledger data and any other records that matter.
# Do not change synchronous to NORMAL or OFF for this server.
if "sqlite" in DATABASE_URL:
    @event.listens_for(engine, "connect")
    def _set_sqlite_wal(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

SessionLocal = sessionmaker(autocommit = False, autoflush = False, bind = engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- --- ---
# This is a database tool that will likely be moved to tools for a series of database tools that are modularized for all databases

def ensure_db_column(engine, table = "users", column = "custom_theme", ctype = "JSON"):
    inspector = inspect(engine)
    # Check if 'users' table exists and if 'custom_theme' is missing
    if table in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns(table)]
        if column not in columns:
            print(f"Migration: '{column}' column missing. Adding now...")
            with engine.connect() as conn:
                # This syntax works for SQLite and PostgreSQL
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ctype}"))
                conn.commit()
            print("Migration successful.")

# Ensure database tables - This should be an update loop with a set breakdown from all changes between versions to capture all migrations
ensure_db_column(engine)