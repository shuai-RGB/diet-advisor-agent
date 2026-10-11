"""画像 & 营养目标计算。

基于 Mifflin-St Jeor 公式估算基础代谢(BMR)，结合活动系数与目标(减脂/增肌/控糖/维持)
计算每日热量与三大营养素目标；蛋白质按每公斤体重系数，脂肪按热量占比，碳水取余量，
确保三者热量之和等于总热量。参考《中国居民膳食指南(2022)》。
"""
from __future__ import annotations

from .. import config


def calc_targets(sex: str, age: int, height_cm: float, weight_kg: float,
                 activity: str, goal: str) -> dict:
    sex = "男" if sex in ("男", "male", "m") else "女"
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if sex == "男" else -161)
    tdee = bmr * config.ACTIVITY_LEVELS.get(activity, 1.375)

    if goal == "减脂":
        calories = tdee - 400
    elif goal == "增肌":
        calories = tdee + 300
    else:
        calories = tdee

    protein_per_kg = {"维持健康": 1.0, "减脂": 1.6, "增肌": 1.8, "控糖": 1.2}.get(goal, 1.0)
    fat_pct = {"减脂": 0.22, "增肌": 0.25, "控糖": 0.28, "维持健康": 0.25}.get(goal, 0.25)

    protein = round(weight_kg * protein_per_kg, 1)
    fat = round(calories * fat_pct / 9.0, 1)
    carb = round(max(0.0, (calories - protein * 4 - fat * 9) / 4.0), 1)

    bmi = round(weight_kg / ((height_cm / 100) ** 2), 1)
    return {
        "sex": sex, "age": age, "height_cm": height_cm, "weight_kg": weight_kg,
        "activity": activity, "goal": goal, "bmi": bmi,
        "bmr": round(bmr, 0), "tdee": round(tdee, 0),
        "calories": round(calories, 0),
        "protein_g": protein, "fat_g": fat, "carb_g": carb,
        "fiber_g": 25.0, "sodium_mg": 2000.0,
    }
