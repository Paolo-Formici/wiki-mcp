import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from wiki_mcp.git_sync import get_sync_metadata, pull_repo_async
from wiki_mcp.scheduler import CronGitSyncScheduler


def test_scheduler_validation(tmp_path: Path):
    # Valid expressions
    s1 = CronGitSyncScheduler(tmp_path, "*/5 * * * *")
    assert s1.cron_expr == "*/5 * * * *"

    s2 = CronGitSyncScheduler(tmp_path, "0 0 * * *")
    assert s2.cron_expr == "0 0 * * *"

    # Invalid expressions should raise ValueError
    with pytest.raises(ValueError, match="Invalid cron expression"):
        CronGitSyncScheduler(tmp_path, "invalid-cron")

    with pytest.raises(ValueError, match="Invalid cron expression"):
        CronGitSyncScheduler(tmp_path, "* * *")  # too few fields


def test_scheduler_seconds_until_next(tmp_path: Path):
    scheduler = CronGitSyncScheduler(tmp_path, "* * * * *")
    # Reference time: 12:00:15 UTC -> next match is 12:01:00 UTC (45 seconds)
    ref_time = datetime(2026, 9, 8, 12, 0, 15, tzinfo=timezone.utc)
    seconds = scheduler.get_seconds_until_next(now=ref_time)
    assert seconds == 45.0


@pytest.mark.anyio
async def test_scheduler_start_and_stop(tmp_path: Path):
    scheduler = CronGitSyncScheduler(tmp_path, "* * * * *")

    with patch.object(scheduler, "get_seconds_until_next", return_value=0.05):
        with patch("wiki_mcp.scheduler.pull_repo_async", new_callable=AsyncMock) as mock_pull:
            mock_pull.return_value = (True, "abc1234", "Already up to date.")

            task = scheduler.start()
            assert not task.done()

            # Allow loop to tick at least once
            await asyncio.sleep(0.12)

            assert mock_pull.call_count >= 1
            mock_pull.assert_called_with(tmp_path, trigger="cron")

            await scheduler.stop()
            assert task.done()


@pytest.mark.anyio
async def test_scheduler_loop_handles_exception_gracefully(tmp_path: Path):
    scheduler = CronGitSyncScheduler(tmp_path, "* * * * *")

    with patch.object(scheduler, "get_seconds_until_next", return_value=0.01):
        with patch("wiki_mcp.scheduler.pull_repo_async", side_effect=RuntimeError("Network error")):
            scheduler.start()
            # Wait briefly; scheduler should log error and not crash
            await asyncio.sleep(0.05)
            assert scheduler._running
            await scheduler.stop()


@pytest.mark.anyio
async def test_concurrent_pull_serialization(tmp_path: Path):
    """Verifies that concurrent calls to pull_repo_async are serialized by the lock."""
    order = []

    async def fake_cmd(wiki_dir, *args):
        order.append("start")
        await asyncio.sleep(0.05)
        order.append("end")
        return 0, "mock commit", ""

    with patch("wiki_mcp.git_sync.git_cmd_async", side_effect=fake_cmd):
        with patch("wiki_mcp.git_sync.get_current_commit", return_value="deadbeef"):
            # Launch two concurrent pulls (e.g. one cron and one webhook)
            results = await asyncio.gather(
                pull_repo_async(tmp_path, trigger="cron"),
                pull_repo_async(tmp_path, trigger="webhook"),
            )

            assert results[0][0] is True
            assert results[1][0] is True
            # Since it's serialized by lock, start/end must not interleave:
            # i.e., start -> end -> start -> end
            assert order == ["start", "end", "start", "end"]

            meta = get_sync_metadata()
            assert meta.last_sync_status == "synced"
            assert meta.last_sync_commit == "deadbeef"

