"""画像 & 目标 Agent：根据身体信息计算每日营养目标。"""
from __future__ import annotations

from .. import config
from ..data import profile as profile_calc


def run(state: dict) -> dict:
    ent = state.get("entities", {})
    sex = ent.get("sex", "男")
    age = int(ent.get("age", 25))
    height_cm = float(ent.get("height_cm", 170))
    weight_kg = float(ent.get("weight_kg", 60))
    activity = ent.get("activity", "轻度")
    goal = ent.get("goal", "维持健康")
    if activity not in config.ACTIVITY_LEVELS:
        activity = "轻度"
    if goal not in config.GOALS:
        goal = "维持健康"

    profile = {"sex": sex, "age": age, "height_cm": height_cm,
               "weight_kg": weight_kg, "activity": activity, "goal": goal}
    targets = profile_calc.calc_targets(sex, age, height_cm, weight_kg, activity, goal)
    return {"profile": profile, "targets": targets}
