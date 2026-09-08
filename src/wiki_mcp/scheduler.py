import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import croniter
from wiki_mcp.git_sync import pull_repo_async
from wiki_mcp.logger import get_logger, log_event

logger = get_logger("wiki_mcp.scheduler")


class CronGitSyncScheduler:
    """
    Background scheduler that periodically runs git pull --ff-only
    on a wiki directory based on a standard 5-field cron expression.
    """

    def __init__(self, wiki_dir: Path, cron_expr: str):
        self.wiki_dir = wiki_dir
        self.cron_expr = cron_expr.strip()

        if not croniter.croniter.is_valid(self.cron_expr):
            raise ValueError(
                f"Invalid cron expression: '{self.cron_expr}'. Standard 5-field format required (e.g. '*/5 * * * *')."
            )

        self._task: Optional[asyncio.Task] = None
        self._running = False

    def get_seconds_until_next(self, now: Optional[datetime] = None) -> float:
        """Calculates seconds remaining until the next cron match."""
        base_time = now or datetime.now(timezone.utc)
        itr = croniter.croniter(self.cron_expr, base_time)
        next_dt = itr.get_next(datetime)
        diff = (next_dt - base_time).total_seconds()
        return max(diff, 1.0)

    async def _run_loop(self):
        log_event(
            logger, 20, "cron_scheduler_started",
            f"Cron sync scheduler started with expression: '{self.cron_expr}'",
            wiki_dir=str(self.wiki_dir),
            cron=self.cron_expr
        )
        while self._running:
            try:
                seconds_to_wait = self.get_seconds_until_next()
                log_event(
                    logger, 10, "cron_scheduler_sleep",
                    f"Cron scheduler waiting {round(seconds_to_wait, 1)}s until next sync tick",
                    sleep_seconds=seconds_to_wait,
                    cron=self.cron_expr
                )
                await asyncio.sleep(seconds_to_wait)

                if not self._running:
                    break

                log_event(
                    logger, 20, "cron_sync_trigger",
                    f"Cron trigger fired for expression '{self.cron_expr}'; starting pull",
                    cron=self.cron_expr
                )
                await pull_repo_async(self.wiki_dir, trigger="cron")

            except asyncio.CancelledError:
                log_event(logger, 20, "cron_scheduler_cancelled", "Cron scheduler task was cancelled")
                break
            except Exception as e:
                log_event(
                    logger, 40, "cron_scheduler_error",
                    f"Unexpected error in cron scheduler loop: {str(e)}"
                )
                await asyncio.sleep(5.0)

    def start(self) -> asyncio.Task:
        """Starts the background cron task if not already running."""
        if self._task and not self._task.done():
            return self._task

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        return self._task

    async def stop(self):
        """Cancels and awaits the background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            log_event(logger, 20, "cron_scheduler_stopped", "Cron sync scheduler stopped")
