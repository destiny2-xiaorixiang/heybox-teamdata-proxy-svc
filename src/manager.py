import random
import re
import time
import aiohttp
import asyncio
import datetime
from itertools import chain
from loguru import logger

from src.counter import Counter
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
    PROXY_FLEX_TIME,
    REQUEST_TIMEOUT,
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
                logger.bind(dev=True).exception("fetch proxy error: ", e)
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
                expire_time = (
                    create_time + datetime.timedelta(seconds=duration) - PROXY_FLEX_TIME
                )
                proxy = ProxyModel(
                    ip=ip_data["ip"],
                    port=ip_data["port"],
                    duration=duration,
                    create_time=create_time,
                    expire_time=expire_time,
                )
                cls.pool.append(proxy)
                logger.bind(dev=True).success("fetch new proxy, {}", proxy)

    @classmethod
    async def get_ip_random(cls) -> ProxyModel | None:
        """
        随机返回一个可用IP，首先会清除过期的IP

        如果IP池为空则抛出ValueError
        """
        cls.pool = [proxy for proxy in cls.pool if not proxy.is_expired]
        if not cls.pool:
            logger.bind(dev=True).warning("proxy pool is empty")
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
                logger.bind(dev=True).exception("fireteam helper error", e)
            await asyncio.sleep(POST_FIRETEAM_RATE)

    @classmethod
    @aretry(delay_seconds=0.5)
    async def fetch_fireteam_data(cls, *, offset=0) -> dict:
        proxy_data = await cls.ip_proxy_manager.get_ip_random()
        kwargs = {"proxy": proxy_data.url_str} if proxy_data else {}
        try:
            async with aiohttp.ClientSession(
                headers={"Accept": "application/json, text/plain, */*"},
                timeout=REQUEST_TIMEOUT,
            ) as session:

                async with session.get(
                    FETCH_HEYBOX_FIRETEAM_URL.format(offset),
                    verify_ssl=False,
                    **kwargs,
                ) as resp:
                    data = await resp.json()
        except Exception as e:
            # cls.ip_proxy_manager.pool.remove(proxy_data)
            logger.bind(dev=True).warning(
                "fetch heybox data error, proxy_data:{proxy_data}, exception:{e}",
                proxy_data=proxy_data,
                e=e,
            )
            raise e

        resp = []
        expire_time = (
            datetime.datetime.now(tz=datetime.timezone.utc) - HISTORY_EXPIRE_DURATION
        )
        for team_data in data["result"]["data_list"]:
            context = team_data["team_data"]["team_text"].replace("\n", "")
            bungie_id = team_data["team_data"]["name"]["value"]

            # 如果组队内容和ID为空，忽略处理
            if not (context and bungie_id):
                continue

            if group := re.match("^/[jJ] *(.+)$", bungie_id):
                bungie_id = group.group(1)
            user_id = team_data["user"]["userid"]
            create_time = team_data["create_at"]
            link_id = team_data["linkid"]

            group_data = GroupData(
                context=context,
                bungie_id=bungie_id,
                link_id=link_id,
                user_id=user_id,
                create_time=create_time,
            )

            # 对于发布时间过久的任务，忽略处理
            if group_data.create_time <= expire_time:
                continue
            resp.append(group_data)

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
        Counter.add_count(
            "fetch_gather_heybox_data",
            1,
            is_time_count=True,
            time_cost=time.time() - start_time,
        )

        group_set: set[GroupData] = set(
            [
                i
                for i in chain(*[j for j in data if not isinstance(j, Exception)])
                if not isinstance(i, Exception)
            ]
        )

        groups = group_set - cls.history_group_set

        logger.bind(dev=True).success("fetch gather heybox data successfully")

        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            resp = await asyncio.gather(
                *[
                    cls._put_fireteam_data(group_data, session=session)
                    for group_data in groups
                ],
                return_exceptions=True,
            )

        sent_set = set([data for data, value in zip(groups, resp) if not value])
        Counter.add_count("group_data_push", len(sent_set))

        # 合入历史记录
        cls.clean_history_set()
        cls.history_group_set |= sent_set

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
                    e = ValueError("发布组队失败", status, msg, group_data)
                    logger.bind(dev=True).warning("post group data fail, {}", e)
                    raise e
