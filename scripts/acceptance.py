"""整体验收：全接口 + 评测 + 聊天(ReAct/报告/记忆) + 可观测性。"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000"
PROFILE = {"sex": "男", "age": 25, "height_cm": 175, "weight_kg": 70, "activity": "中度", "goal": "减脂"}


def get(url):
    return json.load(urllib.request.urlopen(url, timeout=60))


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=90))


def check(name, ok, detail=""):
    ok = bool(ok)
    print(f"  [{'✓' if ok else '✗'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def main():
    print("=" * 56)
    print("健康助手 · 整体验收")
    print("=" * 56)
    passed = []

    # 1. 健康 + 前端
    h = get(BASE + "/api/health")
    passed.append(check("健康检查", h.get("status") == "ok", str(h)))

    # 2. 六类核心能力
    passed.append(check("营养目标", post(BASE + "/api/goal", PROFILE)["report"]["title"]))
    passed.append(check("三餐食谱", post(BASE + "/api/meal-plan", PROFILE)["report"]["title"]))
    passed.append(check("饮食分析", post(BASE + "/api/analyze", {"items": [{"name": "鸡胸肉", "grams": 150}]})["report"]["title"]))
    passed.append(check("附近采购", post(BASE + "/api/where-to-eat", {"city": "北京"})["report"]["title"]))
    passed.append(check("完整方案", post(BASE + "/api/plan/steps", {**PROFILE, "city": "北京"})["result"]["report"]["title"]))
    passed.append(check("知识问答", post(BASE + "/api/query", {"question": "减脂要注意什么"})["report"]["title"]))

    # 3. 聊天：ReAct 报告（多轮追问）
    sid = None
    for msg in ["帮我生成一天饮食锻炼报告", "男", "25", "175", "70", "减脂"]:
        r = post(BASE + "/api/chat", {"message": msg, "session_id": sid})
        sid = r["session_id"]
    passed.append(check("聊天·多轮追问报告", "目标" in r["reply"],
                        r["reply"][:40].replace("\n", " ")))

    # 4. 记忆个性化
    post(BASE + "/api/chat", {"message": "我不吃辣"})
    r2 = post(BASE + "/api/chat", {"message": "我晚餐注意什么"})
    passed.append(check("记忆·记住偏好", "辣" in r2["reply"], r2["reply"][:40].replace("\n", " ")))

    # 5. 可观测性 + 可靠性
    o = get(BASE + "/api/observability")
    rel = o.get("reliability", {})
    passed.append(check("可观测性", o["summary"]["请求数"] >= 1,
                        f"请求数 {o['summary']['请求数']}, 成本 ¥{o['summary']['总成本_元']}"))
    passed.append(check("可靠性状态", not rel["breaker"]["open"],
                        f"熔断 open={rel['breaker']['open']}, 预算 {rel['budget']['used']}/{rel['budget']['budget']}"))

    # 6. 评测指标
    from src.agents.router import classify
    from src.data import food_db, meal_planner, profile as profile_calc
    from src.llm import get_llm
    llm = get_llm()
    intents = json.loads((ROOT / "data/eval/intents.json").read_text(encoding="utf-8"))
    foods = json.loads((ROOT / "data/eval/foods.json").read_text(encoding="utf-8"))
    ic = sum(1 for it in intents if classify(it["message"], llm) == it["intent"])
    df = food_db.load_db()
    fc = sum(1 for it in foods if (lambda r: r and (it["expect"] in r["food_name"] or r["food_name"] in it["expect"]))(food_db.find_food(df, it["query"])))
    t = profile_calc.calc_targets("男", 25, 175, 70, "中度", "减脂")
    plan = meal_planner.plan(t, [], seed=0)
    cal_err = abs(plan["achievement"]["calories"] - 1) * 100
    passed.append(check("评测·意图识别", ic == len(intents), f"{ic}/{len(intents)}"))
    passed.append(check("评测·食物检索", fc == len(foods), f"{fc}/{len(foods)}"))
    passed.append(check("评测·热量偏差", cal_err < 1, f"{cal_err:.1f}%"))

    print("=" * 56)
    ok = sum(passed)
    print(f"验收结果：{ok}/{len(passed)} 项通过")
    print("=" * 56)


if __name__ == "__main__":
    main()
