"""端到端冒烟测试：目标 / 食谱 / 分析 / 去哪吃 / 问答。"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.graph.workflow import (  # noqa: E402
    run_diet_analyze, run_goal, run_meal_plan, run_plan, run_query, run_where_to_eat,
)


def show(title, r):
    print(f"\n===== {title} =====")
    print(json.dumps(r, ensure_ascii=False, indent=2)[:1600])


async def main():
    show("0) 综合方案（多Agent协作）", await run_plan(
        {"sex": "男", "age": 25, "height_cm": 175, "weight_kg": 70,
         "activity": "中度", "goal": "减脂", "city": "北京", "budget": 80,
         "restrictions": ["不吃辣"]}))
    show("1) 营养目标", await run_goal({"sex": "男", "age": 25, "height_cm": 175,
                                        "weight_kg": 70, "activity": "中度", "goal": "减脂"}))
    show("2) 三餐食谱（素食）", await run_meal_plan(
        {"sex": "女", "age": 24, "height_cm": 162, "weight_kg": 52,
         "activity": "轻度", "goal": "减脂"}, restrictions=["素食"], seed=1))
    show("3) 饮食分析", await run_diet_analyze(
        [{"name": "米饭", "grams": 200}, {"name": "鸡胸肉", "grams": 150},
         {"name": "西兰花", "grams": 200}],
        {"sex": "男", "age": 25, "height_cm": 175, "weight_kg": 70,
         "activity": "中度", "goal": "减脂"}))
    show("4) 去哪吃", await run_where_to_eat({"city": "北京", "keywords": "火锅", "budget": 120}))
    show("5) 知识问答", await run_query("减脂期每天蛋白质应该吃多少？"))


if __name__ == "__main__":
    asyncio.run(main())
