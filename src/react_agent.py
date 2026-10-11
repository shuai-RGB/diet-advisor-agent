"""ReAct + 真 tool-calling：LLM 自主决定调用哪个工具、追问什么。

区别于旧的确定性路由（查表式意图分类 + 硬编码状态机），这里让 LLM
在 Thought → Action → Observation 循环里自己推理「缺什么信息、该调哪个工具」。
"""
from __future__ import annotations

import json

from .data import food_db, meal_planner, profile as profile_calc

SYSTEM = (
    "你是「健康助手」，可以调用工具：compute_targets 算营养目标、generate_meals 生成三餐、get_weather 查天气、"
    "search_knowledge 查知识、search_food 查食物、search_markets 找超市。\n"
    "算目标/三餐的必需信息只有：性别、身高、体重、目标。年龄默认25、活动量默认轻度、城市默认北京，都不强制问。\n"
    "规则：只缺必需信息时才 ask_user；信息齐全就直接调对应工具；最后用中文简洁总结（不超过150字）。\n"
    "注意：用户只是表达偏好/忌口（如'我不吃辣'、'我喜欢清淡'）时，简单确认记住即可，不要追问或生成方案。"
)

TOOLS = [
    {"type": "function", "function": {"name": "ask_user",
        "description": "缺少必要信息时向用户提问（如身高、体重、目标、城市）",
        "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}}},
    {"type": "function", "function": {"name": "compute_targets",
        "description": "按身高体重目标计算每日营养目标（热量/蛋白/脂肪/碳水）",
        "parameters": {"type": "object", "properties": {
            "sex": {"type": "string"}, "age": {"type": "integer"}, "height_cm": {"type": "number"},
            "weight_kg": {"type": "number"}, "activity": {"type": "string"}, "goal": {"type": "string"}},
            "required": ["sex", "height_cm", "weight_kg", "goal"]}}},
    {"type": "function", "function": {"name": "generate_meals",
        "description": "按目标生成一日三餐（含烹饪方式）",
        "parameters": {"type": "object", "properties": {
            "sex": {"type": "string"}, "age": {"type": "integer"}, "height_cm": {"type": "number"},
            "weight_kg": {"type": "number"}, "goal": {"type": "string"},
            "restrictions": {"type": "array", "items": {"type": "string"}}},
            "required": ["sex", "height_cm", "weight_kg", "goal"]}}},
    {"type": "function", "function": {"name": "get_weather",
        "description": "查某城市当前天气",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}},
    {"type": "function", "function": {"name": "search_knowledge",
        "description": "检索健康饮食运动知识库",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "search_food",
        "description": "查某种食物的营养成分（每100克）",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "search_markets",
        "description": "找附近超市/菜市场",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}, "location": {"type": "string"}}, "required": ["city"]}}},
]


def _compute_targets(args: dict) -> dict:
    t = profile_calc.calc_targets(
        args.get("sex", "男"), int(args.get("age", 25)), float(args.get("height_cm", 170)),
        float(args.get("weight_kg", 60)), args.get("activity", "轻度"), args.get("goal", "维持健康"))
    return {"热量_千卡": round(t["calories"]), "蛋白质_g": t["protein_g"],
            "脂肪_g": t["fat_g"], "碳水_g": t["carb_g"]}


def _generate_meals(args: dict) -> dict:
    t = profile_calc.calc_targets(args.get("sex", "男"), int(args.get("age", 25)),
                                  float(args.get("height_cm", 170)), float(args.get("weight_kg", 60)),
                                  "轻度", args.get("goal", "维持健康"))
    plan = meal_planner.plan(t, args.get("restrictions") or [], seed=0)
    meals = [{"餐": m["slot"], "食物": [f"{i['food']}({i['cooking']})" for i in m["items"][:4]]}
             for m in plan["meals"]]
    return {"三餐": meals, "合计热量_千卡": round(plan["totals"]["energy_kcal"])}


def _get_weather(args: dict) -> dict:
    from .tools import amap
    r = amap.get_weather(args.get("city", "北京"))
    if "error" in r:
        return {"错误": r["error"]}
    return {"城市": r["city"], "天气": r["weather"], "气温": r["temperature"], "风力": r["windpower"]}


_rag = None


def _search_knowledge(args: dict) -> dict:
    global _rag
    if _rag is None:
        from .rag import retriever
        try:
            _rag = retriever.load()
        except Exception:
            return {"结果": "知识库未就绪"}
    hits = _rag.search(args.get("query", ""), k=3)
    return {"片段": [{"标题": h.get("title", ""), "内容": h.get("text", "")[:120]} for h in hits]}


def _search_food(args: dict) -> dict:
    df = food_db.load_db()
    row = food_db.find_food(df, args.get("name", ""))
    if row is None:
        return {"结果": "未找到该食物"}
    n = food_db.nutrition(row, 100)
    return {"食物": row["food_name"], "类别": row["category"],
            "每100克": {"热量": n["energy_kcal"], "蛋白": n["protein_g"],
                        "脂肪": n["fat_g"], "碳水": n["carb_g"]}}


def _search_markets(args: dict) -> dict:
    from .tools import amap
    city = args.get("city", "北京")
    loc = args.get("location")
    all_pois, seen, pois = [], set(), []
    for kw in ("超市", "菜市场"):
        r = amap.search_around(loc, kw) if loc else amap.search_pois(city, kw, None)
        if "error" not in r:
            all_pois.extend(r.get("pois", []))
    for p in all_pois:
        if p["name"] not in seen:
            seen.add(p["name"])
            pois.append(p)
    return {"附近": [{"名": p["name"], "距离米": p.get("distance_m"), "评分": p.get("rating")}
                    for p in pois[:5]]}


def _exec(name: str, args: dict, location: str | None) -> dict:
    if name == "ask_user":
        return {"__ask__": args.get("question", "能再告诉我一点信息吗？")}
    if name == "compute_targets":
        return _compute_targets(args)
    if name == "generate_meals":
        return _generate_meals(args)
    if name == "get_weather":
        return _get_weather(args)
    if name == "search_knowledge":
        return _search_knowledge(args)
    if name == "search_food":
        return _search_food(args)
    if name == "search_markets":
        return _search_markets(args)
    return {"错误": f"未知工具 {name}"}


def react_chat(message: str, history: list[dict], llm, location: str | None = None,
               city: str | None = None, memories: list[dict] | None = None,
               preferences: list[dict] | None = None, max_iters: int = 6) -> str:
    system = SYSTEM
    if city:
        system += f"\n用户当前城市：{city}。查天气/找超市直接用这个城市，不要追问城市。"
    else:
        system += "\n用户没说城市就用北京，不要追问城市。"
    if memories:
        system += "\n用户的历史偏好（对话里说过的，要记住）：\n- " + "\n- ".join(m["content"] for m in memories[:8])
    if preferences:
        system += "\n用户最近常吃的食物（饮食记录统计）：" + "、".join(p["food"] for p in preferences)
    messages: list[dict] = [{"role": "system", "content": system}]
    for m in history[-8:]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": message})

    for _ in range(max_iters):
        content, tool_calls = llm.chat(messages, TOOLS)
        if not tool_calls:
            return (content or "抱歉，我暂时没想好怎么回答。").strip()
        messages.append({"role": "assistant", "content": content or "", "tool_calls": tool_calls})
        for tc in tool_calls:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except Exception:
                args = {}
            result = _exec(tc["function"].get("name"), args, location)
            if isinstance(result, dict) and result.get("__ask__"):
                return result["__ask__"]
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": json.dumps(result, ensure_ascii=False, default=str)})
    return "抱歉，这个问题有点复杂，我处理不过来了。"
