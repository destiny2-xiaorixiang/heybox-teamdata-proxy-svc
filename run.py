import asyncio
from pathlib import Path
from loguru import logger
from src.manager import FireteamHelper, IpProxyManager
from src.counter import Counter

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

Path("./data/logs").mkdir(parents=True, exist_ok=True)

logger.add(
    "./data/logs/heybox-teamdata-proxy-svc-dev-{time}.log",
    rotation="00:00",
    enqueue=True,
    encoding="utf-8",
    filter=lambda record: record["extra"].get("dev", False),
)
logger.add(
    "./data/logs/heybox-teamdata-proxy-svc-stats-{time}.log",
    rotation="00:00",
    enqueue=True,
    encoding="utf-8",
    filter=lambda record: record["extra"].get("stats", False),
)


if __name__ == "__main__":
    Counter.run()
    while True:
        tasks: list[asyncio.Task] = []
        try:

            logger.bind(dev=True).info("ready to start the server")

            async def main():
                ip_manager = IpProxyManager()
                helper = FireteamHelper()
                tasks.append(asyncio.create_task(ip_manager.run()))
                tasks.append(asyncio.create_task(helper.run()))
                await asyncio.gather(*tasks)

            asyncio.run(main())
        except Exception as e:
            logger.bind(dev=True).exception("server error: ", e)
            for task in tasks:
                task.cancel()
