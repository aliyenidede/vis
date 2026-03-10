import logging
import signal
import sys

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Config
from .db import init_db, close_pool
from .main import run_pipeline, setup_logging
from .bot import VISBot

logger = logging.getLogger(__name__)


def start_scheduler():
    config = Config.load()
    setup_logging(config.output_dir)
    logger.info("VIS scheduler + bot starting")

    pool = init_db(config.database_url)

    # Background scheduler for cron pipeline runs
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_pipeline,
        CronTrigger(hour=8, minute=0, timezone="Europe/Istanbul"),
        args=[config, pool],
        id="vis_daily_run",
        name="Daily VIS Pipeline",
    )
    scheduler.start()
    logger.info("Scheduler started — daily run at 08:00 Istanbul time")

    # Telegram bot with polling (main thread)
    bot = VISBot(config.telegram_bot_token, config.telegram_chat_id, pool, config)
    bot.set_run_callback(lambda: run_pipeline(config, pool))

    def shutdown(signum, frame):
        logger.info("Shutdown signal received")
        bot.stop_polling()
        scheduler.shutdown(wait=False)
        close_pool(pool)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Start bot polling (blocking — keeps process alive)
    logger.info("Bot polling started — listening for commands")
    bot.start_polling()

    # Keep main thread alive
    try:
        signal.pause()
    except AttributeError:
        # Windows doesn't have signal.pause
        import time
        while True:
            time.sleep(60)


if __name__ == "__main__":
    start_scheduler()
