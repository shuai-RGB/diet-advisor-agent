"""批量基准测试：验证食谱规划质量 + 高德接口连通性。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data import meal_planner, profile as profile_calc  # noqa: E402

_MEAT = ("畜肉类及其制品", "禽肉类及其制品", "鱼虾蟹贝类", "蛋类及其制品")


def benchmark_meal_plan(n: int = 30) -> None:
    cal_errors, protein_hit, violations = [], 0, 0
    for i in range(n):
        sex = "男" if i % 2 else "女"
        weight = 55 + (i % 30)
        goal = ["减脂", "增肌", "控糖", "维持健康"][i % 4]
        targets = profile_calc.calc_targets(sex, 25, 170, weight, "轻度", goal)
        restrictions = ["素食"] if i % 3 == 0 else []
        plan = meal_planner.plan(targets, restrictions, seed=i)
        ach = plan["achievement"]
        cal_errors.append(abs(ach["calories"] - 1) * 100)
        if 0.9 <= ach["protein"] <= 1.1:
            protein_hit += 1
        if restrictions == ["素食"]:
            for m in plan["meals"]:
                for it in m["items"]:
                    if it["category"] in _MEAT:
                        violations += 1
    print(f"[meal_plan] 生成 {n} 份：热量平均偏差 {sum(cal_errors)/len(cal_errors):.1f}%，"
          f"蛋白质达标率(±10%) {protein_hit/n*100:.0f}%，素食违规 {violations} 次")


def benchmark_amap() -> None:
    from src.tools import amap
    for city, kw in [("北京", "超市"), ("杭州", "菜市场"), ("成都", "超市")]:
        r = amap.search_pois(city, kw, None, 5)
        if "error" in r:
            print(f"[amap] {city}/{kw}: {r['error']}")
        else:
            print(f"[amap] {city}/{kw}: 共 {r['count']} 条，返回 {len(r['pois'])} 条")


if __name__ == "__main__":
    benchmark_meal_plan(30)
    benchmark_amap()
