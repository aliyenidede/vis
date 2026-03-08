import json
import logging
from datetime import datetime, timezone

import psycopg2
from psycopg2 import pool as pg_pool

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS processed_videos (
    video_id           TEXT PRIMARY KEY,
    title              TEXT NOT NULL,
    channel_title      TEXT,
    published_at       TIMESTAMPTZ,
    url                TEXT,
    status             TEXT NOT NULL,
    retry_count        INTEGER DEFAULT 0,
    first_seen_at      TIMESTAMPTZ NOT NULL,
    processed_at       TIMESTAMPTZ,
    summary            TEXT,
    key_ideas          JSONB,
    category           TEXT,
    transcript_language TEXT
);

CREATE TABLE IF NOT EXISTS run_log (
    id                 SERIAL PRIMARY KEY,
    run_at             TIMESTAMPTZ NOT NULL,
    videos_found       INTEGER,
    videos_processed   INTEGER,
    videos_skipped     INTEGER,
    report_path        TEXT,
    success            BOOLEAN,
    telegram_sent      BOOLEAN DEFAULT FALSE,
    error_message      TEXT
);

CREATE INDEX IF NOT EXISTS idx_pv_status ON processed_videos(status);
CREATE INDEX IF NOT EXISTS idx_pv_first_seen ON processed_videos(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_rl_run_at ON run_log(run_at);
"""


def init_db(database_url: str) -> pg_pool.SimpleConnectionPool:
    logger.info("Initializing database connection pool")
    connection_pool = pg_pool.SimpleConnectionPool(1, 5, dsn=database_url)

    conn = connection_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()
        logger.info("Database schema initialized")
    finally:
        connection_pool.putconn(conn)

    return connection_pool


def get_processed_ids(pool: pg_pool.SimpleConnectionPool) -> set:
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT video_id FROM processed_videos WHERE status IN ('ok', 'gave_up')")
            return {row[0] for row in cur.fetchall()}
    finally:
        pool.putconn(conn)


def get_retryable_videos(pool: pg_pool.SimpleConnectionPool, max_retry_days: int) -> list:
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT video_id, title, channel_title, published_at, url, retry_count
                   FROM processed_videos
                   WHERE status = 'no_transcript'
                     AND first_seen_at > NOW() - INTERVAL '%s days'""",
                (max_retry_days,),
            )
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        pool.putconn(conn)


def upsert_video(pool: pg_pool.SimpleConnectionPool, video_data: dict) -> None:
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO processed_videos
                       (video_id, title, channel_title, published_at, url, status,
                        retry_count, first_seen_at, processed_at, summary, key_ideas,
                        category, transcript_language)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s)
                   ON CONFLICT (video_id) DO UPDATE SET
                       status = EXCLUDED.status,
                       retry_count = EXCLUDED.retry_count,
                       processed_at = EXCLUDED.processed_at,
                       summary = EXCLUDED.summary,
                       key_ideas = EXCLUDED.key_ideas,
                       category = EXCLUDED.category,
                       transcript_language = EXCLUDED.transcript_language""",
                (
                    video_data["video_id"],
                    video_data["title"],
                    video_data.get("channel_title"),
                    video_data.get("published_at"),
                    video_data.get("url"),
                    video_data["status"],
                    video_data.get("retry_count", 0),
                    video_data.get("processed_at"),
                    video_data.get("summary"),
                    json.dumps(video_data["key_ideas"]) if video_data.get("key_ideas") else None,
                    video_data.get("category"),
                    video_data.get("transcript_language"),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def log_run(pool: pg_pool.SimpleConnectionPool, stats: dict) -> int:
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO run_log (run_at, videos_found, videos_processed, videos_skipped,
                                       report_path, success, telegram_sent, error_message)
                   VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    stats.get("videos_found", 0),
                    stats.get("videos_processed", 0),
                    stats.get("videos_skipped", 0),
                    stats.get("report_path"),
                    stats.get("success", False),
                    stats.get("telegram_sent", False),
                    stats.get("error_message"),
                ),
            )
            run_id = cur.fetchone()[0]
        conn.commit()
        return run_id
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def get_unsent_reports(pool: pg_pool.SimpleConnectionPool) -> list:
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, report_path FROM run_log
                   WHERE telegram_sent = FALSE AND report_path IS NOT NULL
                   ORDER BY run_at"""
            )
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        pool.putconn(conn)


def mark_telegram_sent(pool: pg_pool.SimpleConnectionPool, run_id: int) -> None:
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE run_log SET telegram_sent = TRUE WHERE id = %s", (run_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def expire_old_retries(pool: pg_pool.SimpleConnectionPool, max_retry_days: int) -> list:
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE processed_videos
                   SET status = 'gave_up', processed_at = NOW()
                   WHERE status = 'no_transcript'
                     AND first_seen_at <= NOW() - INTERVAL '%s days'
                   RETURNING video_id, title, channel_title, url, retry_count""",
                (max_retry_days,),
            )
            cols = [desc[0] for desc in cur.description]
            expired = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.commit()
        if expired:
            logger.info("Expired %d videos past retry window", len(expired))
        return expired
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def close_pool(pool: pg_pool.SimpleConnectionPool) -> None:
    if pool:
        pool.closeall()
        logger.info("Database connection pool closed")
