"""可靠性工程：重试(指数退避) / 熔断 / 成本预算。"""
from __future__ import annotations

import functools
import random
import time


def retry(max_attempts: int = 3, base_delay: float = 0.5, backoff: float = 2.0):
    """重试 + 指数退避 + 抖动。"""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:  # noqa: BLE001
                    last_exc = e
                    if attempt < max_attempts - 1:
                        time.sleep(base_delay * (backoff ** attempt) + random.uniform(0, 0.1))
            raise last_exc
        return wrapper
    return decorator


class CircuitBreaker:
    """熔断器：连续失败 N 次后开路，冷却期内直接拒绝调用，冷却后自动半开。"""

    def __init__(self, name: str, failure_threshold: int = 3, cooldown_sec: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_sec = cooldown_sec
        self.failures = 0
        self.total_failures = 0
        self.opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.time() - self.opened_at >= self.cooldown_sec:
            # 冷却结束，进入半开状态，允许一次尝试
            self.opened_at = None
            self.failures = 0
            return False
        return True

    def record_failure(self) -> None:
        self.failures += 1
        self.total_failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = time.time()

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def status(self) -> dict:
        return {"name": self.name, "open": self.is_open,
                "failures": self.failures, "total_failures": self.total_failures}


class TokenBudget:
    """token 成本预算：超 80% 告警，超 100% 触发降级。"""

    def __init__(self, budget_tokens: int = 200_000, warn_ratio: float = 0.8):
        self.budget = budget_tokens
        self.warn_ratio = warn_ratio
        self.used = 0
        self.warned = False
        self.exceeded = False

    def consume(self, tokens: int) -> str:
        self.used += tokens
        if self.used >= self.budget and not self.exceeded:
            self.exceeded = True
            return "exceeded"
        if self.used >= self.budget * self.warn_ratio and not self.warned:
            self.warned = True
            return "warn"
        return "ok"

    def status(self) -> dict:
        return {"used": self.used, "budget": self.budget,
                "exceeded": self.exceeded, "ratio": round(self.used / self.budget, 4)}
