"""食谱规划：启发式约束优化，生成满足营养目标的一日三餐。

思路（可解释的启发式，非全局最优）：
1. 按忌口过滤食物库，从主食/蛋白质/蔬菜/水果四大类各取常见食材；
2. 每餐按热量占比(早30/午40/晚30)分配，主食贡献约45%热量、蛋白质约25%、蔬菜固定克数；
3. 计算总热量后整体缩放，使总热量贴近目标，得到接近达标的三餐。
"""
from __future__ import annotations

import numpy as np

from .. import config
from . import food_db

_STAPLE_KW = config.STAPLE_CATS
_PROTEIN_KW = config.PROTEIN_CATS
_VEG_KW = config.VEG_CATS
_FRUIT_KW = config.FRUIT_CATS


def _nut(row: dict, grams: float) -> dict:
    return food_db.nutrition(row, grams)


def _sum_items(meals: list) -> dict:
    total = {"energy_kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0,
             "carb_g": 0.0, "fiber_g": 0.0, "sodium_mg": 0.0, "cholesterol_mg": 0.0}
    for _, items in meals:
        for row, grams in items:
            n = _nut(row, grams)
            for k in total:
                total[k] += n[k]
    return total


def plan(targets: dict, restrictions: list[str] | None = None, seed=None) -> dict:
    restrictions = restrictions or []
    rng = np.random.default_rng(seed)
    df = food_db.load_db()
    df = food_db.filter_df(df, restrictions)

    staples = food_db.pick_common(df, _STAPLE_KW, "staple")
    proteins = food_db.pick_common(df, config.MAIN_PROTEIN_CATS, "protein")
    # 只保留瘦蛋白（低脂高蛋白），排除肋条/五花/肥肉/带骨等高脂部位
    proteins = [p for p in proteins if p["fat_g"] <= 15 and p["protein_g"] >= 6]
    vegs = food_db.pick_common(df, _VEG_KW, "veg")
    fruits = food_db.pick_common(df, _FRUIT_KW, "fruit")
    dairy = food_db.pick_common(df, config.DAIRY_CATS, "dairy")
    # 只保留液态奶/酸奶，排除奶粉/奶疙瘩/炼乳/奶油等浓缩或高脂乳制品
    dairy = [d for d in dairy
             if not any(k in d["food_name"] for k in ("粉", "干", "疙瘩", "炼乳", "奶油", "乳酪", "酪"))]

    # 早餐蛋白（奶+水果）预先固定，剩余蛋白由午晚餐肉/鱼按 4:3 分摊
    breakfast_dairy = rng.choice(dairy) if dairy else None
    breakfast_fruit = rng.choice(fruits) if fruits else None
    breakfast_protein = 0.0
    if breakfast_dairy:
        breakfast_protein += breakfast_dairy["protein_g"] / 100 * 250.0
    if breakfast_fruit:
        breakfast_protein += breakfast_fruit["protein_g"] / 100 * 120.0
    remaining_protein = max(0.0, targets["protein_g"] - breakfast_protein)
    protein_alloc = {"午餐": remaining_protein * 4.0 / 7.0,
                     "晚餐": remaining_protein * 3.0 / 7.0}

    meals: list[tuple[str, list]] = []
    for slot in config.MEAL_SLOTS:
        share = config.MEAL_SHARES[slot]
        items: list[tuple[dict, float]] = []
        if staples:
            s = rng.choice(staples)
            grams = targets["carb_g"] * share / max(1e-6, s["carb_g"] / 100)
            items.append((s, max(30.0, grams)))
        if slot == "早餐":
            if breakfast_dairy:
                items.append((breakfast_dairy, 250.0))
            if breakfast_fruit:
                items.append((breakfast_fruit, 120.0))
        else:
            if proteins:
                p = rng.choice(proteins)
                grams = protein_alloc[slot] / max(1e-6, p["protein_g"] / 100)
                items.append((p, min(300.0, max(30.0, grams))))
            if vegs:
                items.append((rng.choice(vegs), 180.0))
        meals.append((slot, items))

    meals = _tune(meals, targets)
    return _finalize(meals, targets, restrictions)


def _cat_sum(meals, cats, key) -> float:
    s = 0.0
    for _, items in meals:
        for row, grams in items:
            if row["category"] in cats:
                s += row[key] / 100 * grams
    return s


def _scale_cat(meals, cats, scale) -> list:
    return [
        (slot, [(r, max(0.0, g * scale) if r["category"] in cats else g) for r, g in items])
        for slot, items in meals
    ]


def _tune(meals, targets, iters: int = 4) -> list:
    """双旋钮迭代：主蛋白项逼近蛋白质目标，主食项逼近热量目标。"""
    for _ in range(iters):
        t = _sum_items(meals)
        meat_p = _cat_sum(meals, config.MAIN_PROTEIN_CATS, "protein_g")
        non_meat_p = t["protein_g"] - meat_p
        if meat_p > 0.5:
            target_meat_p = max(0.0, targets["protein_g"] - non_meat_p)
            meals = _scale_cat(meals, config.MAIN_PROTEIN_CATS, target_meat_p / meat_p)

        t = _sum_items(meals)
        staple_cal = _cat_sum(meals, config.STAPLE_CATS, "energy_kcal")
        if staple_cal > 10:
            target_staple_cal = targets["calories"] - (t["energy_kcal"] - staple_cal)
            meals = _scale_cat(meals, config.STAPLE_CATS, target_staple_cal / staple_cal)
    return meals


def _finalize(meals, targets, restrictions) -> dict:
    plan_meals = []
    for slot, items in meals:
        meal_items = []
        meal_tot = {"energy_kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0,
                    "carb_g": 0.0, "fiber_g": 0.0, "sodium_mg": 0.0}
        for row, grams in items:
            if grams < 5:
                continue  # 剔除微量/负数条目
            n = _nut(row, grams)
            meal_items.append({
                "food": row["food_name"], "category": row["category"],
                "grams": round(grams, 0), "cooking": food_db.cooking_method(row), **n,
            })
            for k in meal_tot:
                meal_tot[k] += n[k]
        plan_meals.append({"slot": slot, "items": meal_items,
                           "totals": {k: round(v, 1) for k, v in meal_tot.items()}})

    totals = _sum_items(meals)
    achievement = _achievement(totals, targets)
    return {
        "meals": plan_meals,
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "targets": {k: round(v, 1) if isinstance(v, float) else v for k, v in targets.items()},
        "achievement": achievement,
        "restrictions_applied": restrictions,
    }


def _achievement(totals: dict, targets: dict) -> dict:
    def rate(cur_key, tgt_key):
        t = targets.get(tgt_key)
        if not t:
            return 1.0
        return round(totals[cur_key] / t, 3)
    return {
        "calories": rate("energy_kcal", "calories"),
        "protein": rate("protein_g", "protein_g"),
        "fat": rate("fat_g", "fat_g"),
        "carb": rate("carb_g", "carb_g"),
        "fiber": rate("fiber_g", "fiber_g"),
        "sodium": rate("sodium_mg", "sodium_mg"),
    }
