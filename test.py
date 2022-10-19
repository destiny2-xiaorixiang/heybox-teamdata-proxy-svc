import asyncio
import random
import time
from src.manager import FireteamHelper, IpProxyManager

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":

    async def main():
        ip_manager = IpProxyManager()
        helper = FireteamHelper()
        await asyncio.gather(ip_manager.run(), helper.run())

    asyncio.run(main())
