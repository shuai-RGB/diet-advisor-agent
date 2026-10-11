"""食谱规划 Agent：调用约束优化生成一日三餐。"""
from __future__ import annotations

from ..data import meal_planner, profile as profile_calc


def run(state: dict) -> dict:
    targets = state.get("targets")
    out = {}
    if not targets:
        ent = state.get("entities", {})
        targets = profile_calc.calc_targets(
            ent.get("sex", "男"), int(ent.get("age", 25)),
            float(ent.get("height_cm", 170)), float(ent.get("weight_kg", 60)),
            ent.get("activity", "轻度"), ent.get("goal", "维持健康"),
        )
        out["targets"] = targets
    restrictions = state.get("entities", {}).get("restrictions", []) or []
    seed = state.get("entities", {}).get("seed")
    # 收到校验 Agent 的「重新规划请求」时，换种子重试（响应显式消息）
    replan_count = state.get("replan_count", 0)
    if replan_count:
        seed = (seed if seed is not None else 0) + replan_count * 1000
    out["meal_plan"] = meal_planner.plan(targets, restrictions, seed)
    return out
