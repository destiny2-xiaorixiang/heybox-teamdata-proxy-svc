import asyncio
import random
import time
from src.manager import FireteamHelper, IpProxyManager

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    while True:
        tasks: list[asyncio.Task] = []
        try:

            async def main():
                ip_manager = IpProxyManager()
                helper = FireteamHelper()
                tasks.append(asyncio.create_task(ip_manager.run()))
                tasks.append(asyncio.create_task(helper.run()))
                await asyncio.gather(*tasks)

            asyncio.run(main())
        except Exception as e:
            for task in tasks:
                task.cancel()
            # TODO: 异常处理
            ...
