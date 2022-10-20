import random
import re
import time
import aiohttp
import asyncio
import datetime
from itertools import chain

from .util import aretry
from .config import (
    FETCH_PROXY_RATE,
    FETCH_PROXY_URL,
    FETCH_HEYBOX_FIRETEAM_URL,
    HISTORY_EXPIRE_DURATION,
    OFFSET_NUM,
    OFFSET_TIMES,
    POST_FIRETEAM_RATE,
    POST_FIRETEAM_URL,
    SEMAPHORE_NUM,
)
from .model import GroupData, ProxyModel


class IpProxyManager:
    pool: list[ProxyModel] = []

    @classmethod
    async def run(cls):
        while True:
            try:
                await cls.fetch_new_proxy()
            except Exception as e:
                ...
            await asyncio.sleep(FETCH_PROXY_RATE)

    @classmethod
    async def fetch_new_proxy(cls) -> None:
        """
        获取最新的IP代理，封装为`ProxyModel`，加入`pool`
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(FETCH_PROXY_URL) as resp:
                data = await resp.json(content_type=None)
            for ip_data in data["data"]:
                duration = ip_data["during"] * 60
                create_time = datetime.datetime.strptime(
                    ip_data["startTime"], "%Y-%m-%d %H:%M:%S"
                )
                expire_time = create_time + datetime.timedelta(seconds=duration)
                cls.pool.append(
                    ProxyModel(
                        ip=ip_data["ip"],
                        port=ip_data["port"],
                        duration=duration,
                        create_time=create_time,
                        expire_time=expire_time,
                    )
                )

    @classmethod
    async def get_ip_random(cls) -> ProxyModel | None:
        """
        随机返回一个可用IP，首先会清除过期的IP

        如果IP池为空则抛出ValueError
        """
        cls.pool = [proxy for proxy in cls.pool if not proxy.is_expired]
        if not cls.pool:
            return None
        return random.choice(cls.pool)


class FireteamHelper:
    ip_proxy_manager: IpProxyManager = IpProxyManager()
    history_group_set: set[GroupData] = set()
    semaphore: asyncio.Semaphore = asyncio.Semaphore(SEMAPHORE_NUM)

    @classmethod
    async def run(cls):
        while True:
            try:
                await cls.put_fireteam_data()
            except Exception as e:
                ...
            await asyncio.sleep(POST_FIRETEAM_RATE)

    @classmethod
    @aretry(delay_seconds=0.5)
    async def fetch_fireteam_data(cls, *, offset=0) -> dict:
        proxy_data = await cls.ip_proxy_manager.get_ip_random()
        kwargs = {}
        if proxy_data:
            kwargs["proxy"] = proxy_data.url_str
        print(kwargs)
        try:
            async with aiohttp.ClientSession(
                headers={"Accept": "application/json, text/plain, */*"},
                timeout=aiohttp.ClientTimeout(5),
            ) as session:

                async with session.get(
                    FETCH_HEYBOX_FIRETEAM_URL.format(offset),
                    verify_ssl=False,
                    **kwargs,
                ) as resp:
                    data = await resp.json()
        except Exception as e:
            cls.ip_proxy_manager.pool.remove(proxy_data)
            raise e

        resp = []
        for team_data in data["result"]["data_list"]:
            context = team_data["team_data"]["team_text"].replace("\n", "")
            bungie_id = team_data["team_data"]["name"]["value"]
            if not (context and bungie_id):
                continue
            if group := re.match("^/[jJ] *(.+)$", bungie_id):
                bungie_id = group.group(1)
            user_id = team_data["user"]["userid"]
            create_time = team_data["create_at"]
            link_id = team_data["linkid"]

            resp.append(
                GroupData(
                    context=context,
                    bungie_id=bungie_id,
                    link_id=link_id,
                    user_id=user_id,
                    create_time=create_time,
                )
            )
        return resp

    @classmethod
    def clean_history_set(cls):
        expire_time = (
            datetime.datetime.now(tz=datetime.timezone.utc) - HISTORY_EXPIRE_DURATION
        )
        cls.history_group_set = set(
            [
                group
                for group in cls.history_group_set
                if group.create_time > expire_time
            ]
        )

    @classmethod
    async def put_fireteam_data(cls):
        # 获取小黑盒的组队数据
        start_time = time.time()
        data = await asyncio.gather(
            *[
                cls.fetch_fireteam_data(offset=OFFSET_NUM * rate)
                for rate in range(OFFSET_TIMES)
            ],
            return_exceptions=True,
        )
        print(round(time.time() - start_time, 2))
        group_set: set[GroupData] = set(
            [i for i in chain(*data) if not isinstance(i, Exception)]
        )

        groups = group_set - cls.history_group_set

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(5)) as session:
            resp = await asyncio.gather(
                *[
                    cls._put_fireteam_data(group_data, session=session)
                    for group_data in groups
                ],
                return_exceptions=True,
            )

        # 合入历史记录
        cls.clean_history_set()
        cls.history_group_set |= set(
            [data for data, value in zip(groups, resp) if not value]
        )

    @classmethod
    @aretry(delay_seconds=0.5)
    async def _put_fireteam_data(
        cls, group_data: GroupData, *, session: aiohttp.ClientSession
    ):
        await cls.semaphore.acquire()
        try:
            async with session.post(
                POST_FIRETEAM_URL,
                data=group_data.to_dict(),
            ) as req:
                if req.content_type != "application/json":
                    raise aiohttp.ContentTypeError(
                        req.request_info,
                        req.history,
                        code=req.status,
                        message=await req.text(),
                    )
                resp = await req.json()
                status = resp["status"]
                msg = resp["msg"]
                if status != 200:
                    raise ValueError("发布组队失败", status, msg, group_data)
        finally:
            cls.semaphore.release()
