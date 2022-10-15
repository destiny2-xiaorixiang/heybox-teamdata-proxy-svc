from datetime import datetime
from pydantic import BaseModel


class ProxyModel(BaseModel):
    ip: str
    port: str
    create_time: datetime
    expire_time: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.now() >= self.expire_time

    @property
    def url_str(self) -> bool:
        return f"http://{self.ip}:{self.port}"


class GroupData(BaseModel):
    context: str
    bungie_id: str
    user_id: str
    create_time: datetime

    def __hash__(self):
        return int(self.create_time.timestamp())

    def to_dict(self) -> dict:
        return {
            "name": self.bungie_id,
            "context": self.context,
            "source": 3,
            "repeatid": self.user_id,
        }
