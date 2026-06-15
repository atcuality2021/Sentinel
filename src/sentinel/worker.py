# src/sentinel/worker.py
"""Entry point for sentinel-memory-worker."""
from __future__ import annotations

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")


def main() -> None:
    from sentinel.memory.store import db_path
    from sentinel.memory.worker import MemoryWorker
    from sentinel.memory.scheduler import CrawlScheduler

    _db_path = db_path()
    worker = MemoryWorker(_db_path)

    async def _loop() -> None:
        sched = CrawlScheduler(_db_path)

        async def _scheduler_loop() -> None:
            while True:
                sched.tick()
                await asyncio.sleep(60)

        await asyncio.gather(
            worker.run_forever(),
            _scheduler_loop(),
        )

    asyncio.run(_loop())


if __name__ == "__main__":
    main()
