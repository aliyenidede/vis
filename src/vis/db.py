import json
import logging

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

CREATE TABLE IF NOT EXISTS api_usage (
    id                 SERIAL PRIMARY KEY,
    api_name           TEXT NOT NULL,
    video_id           TEXT,
    used_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    success            BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_pv_status ON processed_videos(status);
CREATE INDEX IF NOT EXISTS idx_pv_first_seen ON processed_videos(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_rl_run_at ON run_log(run_at);
CREATE INDEX IF NOT EXISTS idx_api_usage_name ON api_usage(api_name);
CREATE INDEX IF NOT EXISTS idx_api_usage_used_at ON api_usage(used_at);

CREATE TABLE IF NOT EXISTS monitored_channels (
    id              SERIAL PRIMARY KEY,
    channel_input   TEXT NOT NULL,
    channel_name    TEXT,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    active          BOOLEAN DEFAULT TRUE,
    UNIQUE(channel_input)
);

ALTER TABLE processed_videos ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'playlist';
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
            cur.execute(
                "SELECT video_id FROM processed_videos WHERE status IN ('ok', 'gave_up')"
            )
            return {row[0] for row in cur.fetchall()}
    finally:
        pool.putconn(conn)


def get_retryable_videos(
    pool: pg_pool.SimpleConnectionPool, max_retry_days: int
) -> list:
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
                        category, transcript_language, source)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (video_id) DO UPDATE SET
                       status = EXCLUDED.status,
                       retry_count = EXCLUDED.retry_count,
                       processed_at = EXCLUDED.processed_at,
                       summary = EXCLUDED.summary,
                       key_ideas = EXCLUDED.key_ideas,
                       category = EXCLUDED.category,
                       transcript_language = EXCLUDED.transcript_language,
                       source = EXCLUDED.source""",
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
                    json.dumps(video_data["key_ideas"])
                    if video_data.get("key_ideas")
                    else None,
                    video_data.get("category"),
                    video_data.get("transcript_language"),
                    video_data.get("source", "playlist"),
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
            cur.execute(
                "UPDATE run_log SET telegram_sent = TRUE WHERE id = %s", (run_id,)
            )
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


def log_api_usage(
    pool: pg_pool.SimpleConnectionPool, api_name: str, video_id: str, success: bool
) -> None:
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO api_usage (api_name, video_id, success) VALUES (%s, %s, %s)",
                (api_name, video_id, success),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def get_api_usage_this_month(pool: pg_pool.SimpleConnectionPool, api_name: str) -> dict:
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) as total,
                          COUNT(*) FILTER (WHERE success) as successful
                   FROM api_usage
                   WHERE api_name = %s
                     AND used_at >= date_trunc('month', NOW())""",
                (api_name,),
            )
            row = cur.fetchone()
            return {"total": row[0], "successful": row[1]}
    finally:
        pool.putconn(conn)


def get_pipeline_stats(pool: pg_pool.SimpleConnectionPool) -> dict:
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Video counts by status
            cur.execute(
                """SELECT status, COUNT(*) FROM processed_videos GROUP BY status"""
            )
            status_counts = dict(cur.fetchall())

            # Last successful run
            cur.execute(
                """SELECT run_at, videos_processed, telegram_sent
                   FROM run_log WHERE success = TRUE
                   ORDER BY run_at DESC LIMIT 1"""
            )
            last_run = cur.fetchone()

            # Total runs
            cur.execute("SELECT COUNT(*) FROM run_log")
            total_runs = cur.fetchone()[0]

            # Supadata usage this month
            cur.execute(
                """SELECT COUNT(*) FROM api_usage
                   WHERE api_name = 'supadata'
                     AND used_at >= date_trunc('month', NOW())"""
            )
            supadata_this_month = cur.fetchone()[0]

            return {
                "status_counts": status_counts,
                "last_run": {
                    "run_at": last_run[0].isoformat() if last_run else None,
                    "videos_processed": last_run[1] if last_run else 0,
                    "telegram_sent": last_run[2] if last_run else False,
                }
                if last_run
                else None,
                "total_runs": total_runs,
                "supadata_this_month": supadata_this_month,
            }
    finally:
        pool.putconn(conn)


def get_pending_videos(pool: pg_pool.SimpleConnectionPool) -> list:
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT video_id, title, channel_title, status, retry_count, first_seen_at
                   FROM processed_videos
                   WHERE status IN ('no_transcript')
                   ORDER BY first_seen_at DESC"""
            )
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        pool.putconn(conn)


def add_channel(pool: pg_pool.SimpleConnectionPool, channel_input: str):
    """Add a channel to monitor. Re-activates if previously removed.

    Returns:
        (channel_id, is_new) tuple. channel_id is None if already active.
    """
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Check if channel exists (active or inactive)
            cur.execute(
                "SELECT id, active FROM monitored_channels WHERE channel_input = %s",
                (channel_input,),
            )
            existing = cur.fetchone()

            if existing:
                channel_id, active = existing
                if active:
                    conn.rollback()
                    return None, False  # Already active
                # Re-activate previously removed channel
                cur.execute(
                    "UPDATE monitored_channels SET active = TRUE, added_at = NOW() WHERE id = %s",
                    (channel_id,),
                )
                conn.commit()
                return channel_id, False  # Re-activated
            else:
                cur.execute(
                    "INSERT INTO monitored_channels (channel_input) VALUES (%s) RETURNING id",
                    (channel_input,),
                )
                channel_id = cur.fetchone()[0]
                conn.commit()
                return channel_id, True  # New
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def remove_channel(pool: pg_pool.SimpleConnectionPool, channel_id: int) -> None:
    """Soft-delete a monitored channel."""
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE monitored_channels SET active = FALSE WHERE id = %s",
                (channel_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def get_active_channels(pool: pg_pool.SimpleConnectionPool) -> list:
    """Get all active monitored channels."""
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, channel_input, channel_name, added_at
                   FROM monitored_channels
                   WHERE active = TRUE
                   ORDER BY added_at"""
            )
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        pool.putconn(conn)


def update_channel_name(
    pool: pg_pool.SimpleConnectionPool, channel_id: int, name: str
) -> None:
    """Update the resolved display name of a channel."""
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE monitored_channels SET channel_name = %s WHERE id = %s",
                (name, channel_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def close_pool(pool: pg_pool.SimpleConnectionPool) -> None:
    if pool:
        pool.closeall()
        logger.info("Database connection pool closed")
