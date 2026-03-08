import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from main import run

logger = logging.getLogger(__name__)


def start_scheduler():
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run,
        CronTrigger(hour=8, minute=0, timezone="Europe/Istanbul"),
        id="vis_daily_run",
        name="Daily VIS Pipeline",
    )

    logger.info("Scheduler started — next run at 08:00 Istanbul time")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    start_scheduler()
