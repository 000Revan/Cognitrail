"""单进程内存登录限流；不读取客户端伪造的转发头。"""

from collections import OrderedDict
from math import ceil
from threading import Lock
from time import monotonic

from app.core.exceptions import AppError


class LoginRateLimiter:
    """固定窗口与有界键存储；进程重启会清空，多 worker 不共享。"""

    def __init__(self, limit: int, window_seconds: int, max_keys: int = 10000, clock=monotonic):
        self.limit = limit
        self.window = window_seconds
        self.max_keys = max_keys
        self.clock = clock
        self._buckets: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self._lock = Lock()

    @property
    def key_count(self) -> int:
        return len(self._buckets)

    def check(self, key: str) -> None:
        """按来源 IP 计所有登录尝试，超限返回 429。"""
        with self._lock:
            now = self.clock()
            start, count = self._buckets.get(key, (now, 0))
            if now - start >= self.window:
                start, count = now, 0
            if count >= self.limit:
                raise AppError(
                    429,
                    "LOGIN_RATE_LIMITED",
                    "登录尝试过于频繁，请稍后再试",
                    {"retryAfterSeconds": max(1, ceil(self.window - (now - start)))},
                )
            self._buckets[key] = (start, count + 1)
            self._buckets.move_to_end(key)
            while len(self._buckets) > self.max_keys:
                self._buckets.popitem(last=False)
