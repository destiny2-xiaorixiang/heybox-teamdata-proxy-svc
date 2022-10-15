import random
import aiohttp
import asyncio
import datetime
from itertools import chain

from .util import aretry
from .config import (
    FETCH_PROXY_URL,
    FETCH_HEYBOX_FIRETEAM_URL,
    HISTORY_EXPIRE_DURATION,
    OFFSET_NUM,
    OFFSET_TIMES,
    POST_FIRETEAM_URL,
    PROXY_EXPIRE_DURATION,
)
from .model import GroupData, ProxyModel


class IpProxyManager:
    pool: list[ProxyModel] = []

    @classmethod
    async def fetch_new_proxy(cls) -> None:
        """
        获取最新的IP代理，封装为`ProxyModel`，加入`pool`
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(FETCH_PROXY_URL) as resp:
                data = await resp.json(content_type=None)
            create_time = datetime.datetime.now()
            expire_time = create_time + PROXY_EXPIRE_DURATION
            cls.pool.extend(
                [
                    ProxyModel(
                        ip=ip_data["IP"],
                        port=ip_data["Port"],
                        create_time=create_time,
                        expire_time=expire_time,
                    )
                    for ip_data in data["data"]
                ]
            )

    @classmethod
    async def get_ip_random(cls) -> ProxyModel:
        """
        随机返回一个可用IP

        首先会清除过期的IP，如果没有可用的IP则重新获取
        """
        cls.pool = [proxy for proxy in cls.pool if not proxy.is_expired]
        if not cls.pool:
            await cls.fetch_new_proxy()
        return random.choice(cls.pool)


class FireteamHelper:
    ip_proxy_manager: IpProxyManager = IpProxyManager()
    history_group_set: set[GroupData] = set()

    @classmethod
    async def fetch_fireteam_data(cls, *, offset=0) -> dict:
        proxy_data = await cls.ip_proxy_manager.get_ip_random()
        async with aiohttp.ClientSession(
            headers={"Accept": "application/json, text/plain, */*"}
        ) as session:
            async with session.get(
                FETCH_HEYBOX_FIRETEAM_URL.format(offset),
                verify_ssl=False,
                proxy=proxy_data.url_str,
            ) as resp:
                data = await resp.json()

        resp = []
        for team_data in data["result"]["data_list"]:
            context = team_data["team_data"]["team_text"].replace("\n", "")
            bungie_id = team_data["team_data"]["name"]["value"]
            if not (context and bungie_id):
                continue
            user_id = team_data["user"]["userid"]
            create_time = team_data["create_at"]

            resp.append(
                GroupData(
                    context=context,
                    bungie_id=bungie_id,
                    user_id=user_id,
                    create_time=create_time,
                )
            )
        return resp

    @classmethod
    def clean_history_set(cls):
        expire_time = datetime.datetime.now() - HISTORY_EXPIRE_DURATION
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
        data = await asyncio.gather(
            *[
                cls.fetch_fireteam_data(offset=OFFSET_NUM * rate)
                for rate in range(OFFSET_TIMES - 1)
            ]
        )
        group_set: set[GroupData] = set(chain(*data))

        groups = [
            group_data
            for group_data in group_set
            if group_data not in cls.history_group_set
        ]
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(5)) as session:
            resp = await asyncio.gather(
                *[
                    cls._put_fireteam_data(group_data, session=session)
                    for group_data in groups
                ],
                return_exceptions=True
            )

        # 合入历史记录
        cls.clean_history_set()
        cls.history_group_set |= group_set

    @staticmethod
    @aretry(delay_seconds=0.5)
    async def _put_fireteam_data(
        group_data: GroupData, *, session: aiohttp.ClientSession
    ):
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
