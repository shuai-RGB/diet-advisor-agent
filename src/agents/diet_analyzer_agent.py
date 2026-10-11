"""饮食分析 Agent：分析已摄入食物，对比目标给出诊断。"""
from __future__ import annotations

from ..data import diet_analyzer, profile as profile_calc


def run(state: dict) -> dict:
    ent = state.get("entities", {})
    raw_items = ent.get("items") or []
    items = [(str(it["name"]), float(it.get("grams", 100))) for it in raw_items]

    targets = state.get("targets")
    out = {}
    # 若带了画像字段则自动计算目标
    if not targets and any(k in ent for k in ("height_cm", "weight_kg", "age")):
        targets = profile_calc.calc_targets(
            ent.get("sex", "男"), int(ent.get("age", 25)),
            float(ent.get("height_cm", 170)), float(ent.get("weight_kg", 60)),
            ent.get("activity", "轻度"), ent.get("goal", "维持健康"),
        )
        out["targets"] = targets

    out["diet_analysis"] = diet_analyzer.analyze(items, targets)
    return out
