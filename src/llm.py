"""LLM 可插拔大脑 + 可靠性（重试/熔断/降级/成本预算）。

设计意图：大模型是 Agent 的「大脑」，负责意图路由、推荐文案、报告摘要；
营养计算、食谱规划、约束校验等数值逻辑走确定性算法，不交给 LLM。
LLM 不可用时（无 key / 熔断开路 / 重试耗尽）自动降级到规则引擎，系统离线也能跑。
"""
from __future__ import annotations

import os
import time
from typing import Optional

from .reliability import CircuitBreaker, TokenBudget

_token_meter = {"prompt": 0, "completion": 0, "calls": 0}
_llm_breaker = CircuitBreaker("llm", failure_threshold=3, cooldown_sec=60.0)
_token_budget = TokenBudget(budget_tokens=200_000, warn_ratio=0.8)


def _record_usage(usage) -> None:
    global _token_meter
    if usage:
        _token_meter["prompt"] += getattr(usage, "prompt_tokens", 0) or 0
        _token_meter["completion"] += getattr(usage, "completion_tokens", 0) or 0
        _token_meter["calls"] += 1
        status = _token_budget.consume(getattr(usage, "total_tokens", 0) or 0)
        if status in ("warn", "exceeded"):
            print(f"[budget] token 预算 {status}：已用 {_token_budget.used}/{_token_budget.budget}")


def token_snapshot() -> dict:
    """返回累计 token 用量（用于按请求做增量）。"""
    return dict(_token_meter)


def reliability_status() -> dict:
    return {"breaker": _llm_breaker.status(), "budget": _token_budget.status()}


class LLMClient:
    name = "base"
    supports_tools = False

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        raise NotImplementedError

    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None) -> tuple[str, list[dict]]:
        return self.complete(messages[-1]["content"]), []


class RuleBasedLLM(LLMClient):
    name = "rule-based"

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        return ""


class OpenAICompatLLM(LLMClient):
    name = "llm"
    supports_tools = True

    def __init__(self, api_key: str, base_url: str, model: str):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def _request(self, messages: list[dict], tools=None, max_attempts: int = 3):
        """带重试(指数退避) + 熔断的底层请求；失败返回 None（触发降级）。"""
        for attempt in range(max_attempts):
            if _llm_breaker.is_open:
                return None
            kwargs = {"model": self._model, "messages": messages, "temperature": 0.2}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            try:
                resp = self._client.chat.completions.create(**kwargs)
                _llm_breaker.record_success()
                return resp
            except Exception:
                _llm_breaker.record_failure()
                if attempt < max_attempts - 1:
                    time.sleep(0.5 * (2 ** attempt))
        return None

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self._request(messages)
        if resp is None:
            return ""  # 降级：调用方走兜底
        _record_usage(resp.usage)
        return (resp.choices[0].message.content or "").strip()

    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None) -> tuple[str, list[dict]]:
        resp = self._request(messages, tools)
        if resp is None:
            return "", []  # 降级
        _record_usage(resp.usage)
        msg = resp.choices[0].message
        content = (msg.content or "").strip()
        tool_calls = []
        for t in (msg.tool_calls or []):
            tool_calls.append({
                "id": t.id, "type": "function",
                "function": {"name": t.function.name, "arguments": t.function.arguments},
            })
        return content, tool_calls


def get_llm() -> LLMClient:
    from . import config
    config.load_env()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    if api_key and base_url and model and not _llm_breaker.is_open:
        try:
            return OpenAICompatLLM(api_key, base_url, model)
        except Exception:
            return RuleBasedLLM()
    return RuleBasedLLM()
