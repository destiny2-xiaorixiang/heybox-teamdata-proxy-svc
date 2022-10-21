import time
from loguru import logger
from threading import Thread

from src.config import COUNTER_LOG_INTERVAL
from src.model import BaseCountData, TimeCountData


class Counter:
    counter_dict: dict[str, BaseCountData | TimeCountData] = {}

    @classmethod
    def add_count(
        cls, key: str, num: int, *, is_time_count=False, time_cost: float = 0.0
    ):
        if key not in cls.counter_dict:
            cls.counter_dict[key] = (
                TimeCountData(count_name=key)
                if is_time_count
                else BaseCountData(count_name=key)
            )
        cls.counter_dict[key].count += num
        if is_time_count:
            cls.counter_dict[key].time_cost += time_cost

    @classmethod
    def reset(cls):
        cls.counter_dict = {}

    @classmethod
    def _log(cls):
        for count in cls.counter_dict.values():
            if isinstance(count, TimeCountData):
                logger.bind(stats=True).info(
                    "{}, seconds_per_count={}", count.dict(), count.cost_time_per_count
                )
            else:
                logger.bind(stats=True).info(count.dict())

    @classmethod
    def log(cls):
        while True:
            cls._log()
            cls.reset()
            time.sleep(COUNTER_LOG_INTERVAL)

    @classmethod
    def run(cls):
        thread = Thread(target=cls.log)
        thread.daemon = True
        thread.start()
        logger.bind(dev=True).info("counter start")
