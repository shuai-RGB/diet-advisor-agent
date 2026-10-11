"""饮食记录分析：输入吃了什么 -> 总营养 -> 对比目标 -> 诊断建议。"""
from __future__ import annotations

from . import food_db


def analyze(items: list[tuple[str, float]], targets: dict | None = None) -> dict:
    df = food_db.load_db()
    rows = []
    for name, grams in items:
        row = food_db.find_food(df, str(name))
        if row is None:
            rows.append({"name": str(name), "grams": grams, "found": False})
            continue
        n = food_db.nutrition(row, grams)
        rows.append({"name": row["food_name"], "grams": grams, "found": True,
                     "category": row["category"], **n})

    totals = {"energy_kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0,
              "carb_g": 0.0, "fiber_g": 0.0, "sodium_mg": 0.0, "cholesterol_mg": 0.0}
    for r in rows:
        if not r.get("found"):
            continue
        for k in totals:
            totals[k] += r.get(k, 0)

    diagnosis: list[str] = []
    if targets:
        checks = [
            ("energy_kcal", "热量", "calories"),
            ("protein_g", "蛋白质", "protein_g"),
            ("fat_g", "脂肪", "fat_g"),
            ("carb_g", "碳水", "carb_g"),
            ("fiber_g", "膳食纤维", "fiber_g"),
            ("sodium_mg", "钠", "sodium_mg"),
        ]
        for key, label, tkey in checks:
            t = targets.get(tkey)
            if not t:
                continue
            cur = totals[key]
            pct = cur / t
            if pct < 0.75:
                diagnosis.append(f"{label}摄入不足（{cur:.0f} / 目标 {t:.0f}）")
            elif pct > 1.35 and key == "sodium_mg":
                diagnosis.append(f"{label}摄入偏高（{cur:.0f} mg / 建议 ≤{t:.0f} mg）")
            elif pct > 1.25 and key != "sodium_mg":
                diagnosis.append(f"{label}摄入偏高（{cur:.0f} / 目标 {t:.0f}）")

    return {
        "items": rows,
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "targets": targets,
        "diagnosis": diagnosis,
    }
