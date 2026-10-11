"""评测体系：意图识别 / 食物库检索 / 食谱规划质量。

用法：
    python scripts/eval.py
输出控制台报告，并保存 data/eval/report.json。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agents.router import classify  # noqa: E402
from src.data import food_db, meal_planner, profile as profile_calc  # noqa: E402
from src.llm import get_llm  # noqa: E402

_MEAT = ("畜肉类及其制品", "禽肉类及其制品", "鱼虾蟹贝类", "蛋类及其制品")


def eval_intent(dataset: list[dict]) -> dict:
    llm = get_llm()
    correct, errors = 0, []
    for item in dataset:
        got = classify(item["message"], llm)
        if got == item["intent"]:
            correct += 1
        else:
            errors.append({"message": item["message"], "expect": item["intent"], "got": got})
    total = len(dataset)
    return {"准确率": f"{correct}/{total} = {correct/total*100:.0f}%", "错误": errors}


def eval_food_search(dataset: list[dict]) -> dict:
    df = food_db.load_db()
    correct, errors = 0, []
    for item in dataset:
        row = food_db.find_food(df, item["query"])
        got = row["food_name"] if row else None
        # 期望名作为子串命中即可（如 米饭 → 粳米饭）
        if got and (item["expect"] in got or got in item["expect"]):
            correct += 1
        else:
            errors.append({"query": item["query"], "expect": item["expect"], "got": got})
    total = len(dataset)
    return {"准确率": f"{correct}/{total} = {correct/total*100:.0f}%", "错误": errors}


def eval_meal_plan(n: int = 30) -> dict:
    cal_errs, protein_hit, veg_violations = [], 0, 0
    for i in range(n):
        sex = "男" if i % 2 else "女"
        weight = 55 + (i % 30)
        goal = ["减脂", "增肌", "控糖", "维持健康"][i % 4]
        targets = profile_calc.calc_targets(sex, 25, 170, weight, "轻度", goal)
        restrictions = ["素食"] if i % 3 == 0 else []
        plan = meal_planner.plan(targets, restrictions, seed=i)
        ach = plan["achievement"]
        cal_errs.append(abs(ach["calories"] - 1) * 100)
        if 0.9 <= ach["protein"] <= 1.1:
            protein_hit += 1
        if restrictions == ["素食"]:
            for m in plan["meals"]:
                for it in m["items"]:
                    if it["category"] in _MEAT:
                        veg_violations += 1
    return {
        "热量平均偏差": f"{sum(cal_errs)/len(cal_errs):.1f}%",
        "蛋白质达标率(±10%)": f"{protein_hit/n*100:.0f}%",
        "素食违规次数": veg_violations,
        "样本数": n,
    }


def main() -> None:
    data_dir = ROOT / "data" / "eval"
    intents = json.loads((data_dir / "intents.json").read_text(encoding="utf-8"))
    foods = json.loads((data_dir / "foods.json").read_text(encoding="utf-8"))

    t0 = time.time()
    report = {
        "意图识别": eval_intent(intents),
        "食物库检索": eval_food_search(foods),
        "食谱规划": eval_meal_plan(30),
    }
    elapsed = time.time() - t0

    print("=" * 50)
    print("健康助手 · 评测报告")
    print("=" * 50)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n总耗时 {elapsed:.1f}s")

    out = data_dir / "report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已保存 → {out.relative_to(ROOT)}")

    # 单独保存错误用例，方便回看
    errors = {
        "时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "意图识别": report["意图识别"]["错误"],
        "食物库检索": report["食物库检索"]["错误"],
    }
    err_path = data_dir / "errors.json"
    err_path.write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"错误用例已保存 → {err_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
