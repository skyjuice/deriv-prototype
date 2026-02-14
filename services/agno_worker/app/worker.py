from __future__ import annotations

import os

from redis import Redis
from rq import Connection, Worker


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def main() -> None:
    conn = Redis.from_url(REDIS_URL)
    with Connection(conn):
        worker = Worker(["recon"])
        worker.work()


if __name__ == "__main__":
    main()
