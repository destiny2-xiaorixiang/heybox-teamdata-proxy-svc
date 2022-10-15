import asyncio
from src.manager import FireteamHelper

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":

    async def main():
        helper = FireteamHelper()
        data = await helper.put_fireteam_data()
        ...

    asyncio.run(main())
