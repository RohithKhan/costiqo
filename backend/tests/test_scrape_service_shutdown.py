import asyncio

import pytest

from app.services.scrape_service import ScrapeService


@pytest.mark.asyncio
async def test_close_background_tasks_cancels_and_awaits_tracked_tasks():
    service = object.__new__(ScrapeService)
    service._background_tasks = set()
    started = asyncio.Event()
    finalized = asyncio.Event()

    async def background_work() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finalized.set()

    task = asyncio.create_task(background_work())
    service._track_background_task(task)
    await started.wait()

    await service.close_background_tasks()

    assert task.cancelled()
    assert finalized.is_set()
    assert not service._background_tasks
