import aiohttp
import datetime

FETCH_PROXY_URL = "https://api.xiaoxiangdaili.com/ip/get?appKey=899903058900045824&appSecret=8JtDH53F&cnt=&wt=json"
FETCH_HEYBOX_FIRETEAM_URL = "https://api.xiaoheihe.cn/game/h5_activity/common_team/data?appid=1085660&need_list=1&offset={}"
POST_FIRETEAM_URL = "https://api.vforgame.com/platform/teampush"

REQUEST_TIMEOUT = aiohttp.ClientTimeout(5)
HISTORY_EXPIRE_DURATION = datetime.timedelta(minutes=30)  # 本地内存缓存的历史组队信息
OFFSET_NUM = 30  # 单次获取的长度
OFFSET_TIMES = 3  # 获取的次数

SEMAPHORE_NUM = 40

FETCH_PROXY_RATE = 10  # 获取代理的时间间隔，10s
COUNTER_LOG_INTERVAL = 10 # 计数统计的时间间隔
