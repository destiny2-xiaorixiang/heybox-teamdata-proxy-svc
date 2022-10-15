import datetime


FETCH_PROXY_URL = "http://api.xiequ.cn/VAD/GetIp.aspx?act=get&uid=100286&vkey=E563D4546E60A49FF6BC536BE14F8BBF&num=1&time=30&plat=0&re=0&type=0&so=1&ow=1&spl=1&addr=&db=1"
FETCH_HEYBOX_FIRETEAM_URL = "https://api.xiaoheihe.cn/game/h5_activity/common_team/data?appid=1085660&need_list=1&offset={}"
POST_FIRETEAM_URL = "https://api.vforgame.com/platform/teampush"

PROXY_EXPIRE_DURATION = datetime.timedelta(seconds=25)  # 单个代理的过期时间
HISTORY_EXPIRE_DURATION = datetime.timedelta(hours=1)
OFFSET_NUM = 30  # 单次获取的长度
OFFSET_TIMES = 4  # 获取的次数
