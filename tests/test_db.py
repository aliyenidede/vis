import os
import pytest
from vis.db import (
    init_db,
    close_pool,
    get_processed_ids,
    get_retryable_videos,
    upsert_video,
    log_run,
    get_unsent_reports,
    mark_telegram_sent,
    expire_old_retries,
)

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://vis:changeme@localhost:5432/vis_test"
)

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — skipping DB tests",
)


@pytest.fixture
def pool():
    p = init_db(DATABASE_URL)
    conn = p.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM run_log")
            cur.execute("DELETE FROM processed_videos")
        conn.commit()
    finally:
        p.putconn(conn)
    yield p
    close_pool(p)


def test_init_db_creates_tables(pool):
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM processed_videos")
            assert cur.fetchone()[0] == 0
    finally:
        pool.putconn(conn)


def test_upsert_and_get_processed(pool):
    upsert_video(
        pool,
        {
            "video_id": "v1",
            "title": "Test",
            "status": "ok",
            "summary": "sum",
            "key_ideas": ["a"],
            "category": "Tutorial",
        },
    )

    ids = get_processed_ids(pool)
    assert "v1" in ids


def test_upsert_update(pool):
    upsert_video(
        pool,
        {
            "video_id": "v2",
            "title": "Test",
            "status": "no_transcript",
            "retry_count": 1,
        },
    )
    upsert_video(
        pool,
        {
            "video_id": "v2",
            "title": "Test",
            "status": "ok",
            "retry_count": 1,
            "summary": "done",
            "key_ideas": ["b"],
            "category": "News",
        },
    )

    ids = get_processed_ids(pool)
    assert "v2" in ids


def test_log_run_and_unsent(pool):
    run_id = log_run(
        pool,
        {
            "videos_found": 5,
            "videos_processed": 3,
            "videos_skipped": 2,
            "report_path": "/tmp/test.pdf",
            "success": True,
            "telegram_sent": False,
        },
    )

    unsent = get_unsent_reports(pool)
    assert any(r["id"] == run_id for r in unsent)

    mark_telegram_sent(pool, run_id)
    unsent = get_unsent_reports(pool)
    assert not any(r["id"] == run_id for r in unsent)
