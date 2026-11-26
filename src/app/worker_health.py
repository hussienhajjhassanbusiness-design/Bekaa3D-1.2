"""The worker container's health probe: arq's own check, without importing the app.

`arq app.worker.WorkerSettings --check` reads the heartbeat the worker writes to Redis,
but it has to import `app.worker`, and with it the whole application, to find the Redis
settings. On a development machine where `./src` is bind-mounted from a Windows host,
that import takes 16-30 s, longer than the healthcheck's timeout. So the probe always
timed out and marked a working worker unhealthy.

This module does the same check (`arq.worker.async_check_health`: the default queue's
heartbeat key, which the worker refreshes while its poll loop runs) with the same Redis
URL (`REDIS_URL`, as `app.core.config.Settings.redis_url` reads it). It imports only `arq`
and the standard library, so it answers in about a second. Exit 0 = healthy, 1 = no
heartbeat. Run as `python -m app.worker_health`.
"""

import asyncio
import os
import sys

from arq.connections import RedisSettings
from arq.worker import async_check_health


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(os.environ["REDIS_URL"])


def main() -> int:
    return asyncio.run(async_check_health(redis_settings()))


if __name__ == "__main__":
    sys.exit(main())
