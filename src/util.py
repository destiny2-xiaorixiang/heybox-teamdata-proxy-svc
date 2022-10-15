import asyncio
import functools
from itertools import count


def aretry(
    attemps: int = 3,
    delay_seconds: int | float = 2,
):
    def outer(fn):
        functools.wraps(fn)

        async def inner(*args, **kwargs):
            for cnt in count(1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as e:
                    # 如果第三次还是失败则抛出异常
                    if cnt >= attemps:
                        raise e
                    await asyncio.sleep(delay_seconds)

        return inner

    return outer
