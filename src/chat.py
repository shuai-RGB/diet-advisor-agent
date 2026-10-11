"""健康助手聊天：多轮记忆 + 画像记忆 + 追问澄清 + 意图路由。"""
from __future__ import annotations

import re

from .agents.router import classify, extract_entities
from .data import storage
from .llm import get_llm
from .react_agent import react_chat

_REPORT_FIELDS = [
    ("sex", "性别（男/女）"),
    ("age", "年龄"),
    ("height_cm", "身高（厘米）"),
    ("weight_kg", "体重（公斤）"),
    ("goal", "目标（减脂/增肌/维持健康/控糖）"),
]

_BRIEF = {
    "report": "已生成一天饮食锻炼报告",
    "goal": "已计算每日营养目标",
    "meal_plan": "已生成一日三餐",
    "plan_all": "已生成完整方案",
    "where_to_eat": "已查找附近采购点",
    "exercise": "已生成锻炼建议",
    "weather": "已查询天气",
    "diet_analyze": "已记录今日饮食",
    "query": "已解答问题",
}

SYSTEM = "你是「做菜智能助手」里的健康助手，擅长饮食、营养、菜谱、锻炼等。回答专业、简洁、友好，多用建议而不是说教。"
_PROFILE_KEYS = ["sex", "age", "height_cm", "weight_kg", "activity", "goal", "city", "location"]
_PREF_KW = ("喜欢", "爱吃", "不爱", "不吃", "忌", "偏好", "最近在", "要控糖", "要减脂", "要增肌", "过敏")


def _save_memory_if_any(message: str) -> None:
    """把简洁的偏好表述存为长期记忆。"""
    if len(message) > 60:
        return
    if any(k in message for k in _PREF_KW):
        existing = [m["content"] for m in storage.get_memories("default", 50)]
        if message not in existing:
            storage.save_memory("default", message)


async def chat(message: str, session_id: str | None = None, location: str | None = None,
               city: str | None = None) -> dict:
    storage.init_db()
    session_id = session_id or storage.new_session_id()
    history = storage.get_history(session_id, 10)
    llm = get_llm()

    if llm.supports_tools:
        memories = storage.get_memories("default", 10)
        preferences = storage.get_preferences("default", 5)
        reply = react_chat(message, history, llm, location, city, memories, preferences)
        _save_memory_if_any(message)
        storage.save_message(session_id, "user", message)
        storage.save_message(session_id, "assistant", reply)
        return {"reply": reply, "session_id": session_id, "intent": "react", "brief": "已完成对话"}

    intent = classify(message, llm)
    entities = extract_entities(message)
    if location:
        entities["location"] = location

    # 画像记忆：新字段覆盖，缺失用历史画像补
    profile = storage.get_profile(session_id)
    for k in _PROFILE_KEYS:
        if k in entities and entities[k] is not None:
            profile[k] = entities[k]
    if any(k in entities for k in _PROFILE_KEYS):
        storage.save_profile(session_id, profile)

    pending = profile.get("_pending")

    if pending == "report":
        missing = _missing(profile)
        if missing:
            _absorb_answer(profile, missing[0], message)
        storage.save_profile(session_id, profile)
        if _missing(profile):
            reply = f"好的，还需要你的{_next_question(profile)}。"
        else:
            profile.pop("_pending", None)
            storage.save_profile(session_id, profile)
            reply = await _report(profile)
    elif pending == "exercise" and profile.get("city"):
        profile.pop("_pending", None)
        storage.save_profile(session_id, profile)
        reply = _exercise_advice(profile)
    elif pending == "exercise":
        reply = "你在哪个城市呢？告诉我城市（比如北京、上海），我查下当地天气再给你锻炼建议。"
    elif intent == "report":
        if _missing(profile):
            profile["_pending"] = "report"
            storage.save_profile(session_id, profile)
            reply = f"我来帮你生成一天的饮食锻炼报告，先了解几个信息。你的{_next_question(profile)}？"
        else:
            reply = await _report(profile)
    elif intent == "exercise":
        if not profile.get("city"):
            profile["_pending"] = "exercise"
            storage.save_profile(session_id, profile)
            reply = "好的，你想在哪个城市锻炼？我先查下当地天气，再结合你的目标给建议。"
        else:
            reply = _exercise_advice(profile)
    elif intent == "weather":
        reply = _weather_reply(profile)
    elif intent == "diet_analyze":
        reply = _diet_log(message)
    elif intent in ("goal", "meal_plan", "plan_all", "where_to_eat"):
        reply = await _capability(intent, profile)
    else:
        reply = _converse(message, history, llm)

    storage.save_message(session_id, "user", message)
    storage.save_message(session_id, "assistant", reply)
    return {"reply": reply, "session_id": session_id, "intent": intent,
            "brief": _BRIEF.get(intent, "")}


def _profile(profile: dict) -> dict:
    return {
        "sex": profile.get("sex", "男"),
        "age": int(profile.get("age", 25)),
        "height_cm": float(profile.get("height_cm", 170)),
        "weight_kg": float(profile.get("weight_kg", 60)),
        "activity": profile.get("activity", "轻度"),
        "goal": profile.get("goal", "维持健康"),
    }


def _weather_reply(profile: dict) -> str:
    from .tools import amap
    city = profile.get("city")
    if not city:
        return "你在哪个城市？我帮你查天气。"
    w = amap.get_weather(city)
    if "error" in w:
        return f"抱歉，{w['error']}。"
    return (f"{w['city']}今天：{w['weather']}，气温 {w['temperature']}℃，"
            f"{w['winddirection']}风 {w['windpower']}级，湿度 {w['humidity']}%。")


def _exercise_advice(profile: dict) -> str:
    from .tools import amap
    w = amap.get_weather(profile.get("city"))
    if "error" in w:
        return f"抱歉，{w['error']}。可以换个城市试试。"
    weather = w.get("weather", "")
    temp = float(w.get("temperature", 25))
    goal = profile.get("goal", "维持健康")
    bad = any(k in weather for k in ("雨", "雪", "雷", "霾"))
    if bad:
        venue = f"今天{w['city']}「{weather}」，建议室内运动"
    elif temp < 5 or temp > 35:
        venue = f"今天{w['city']}气温 {temp}℃，不太适合户外，建议室内"
    else:
        venue = f"今天{w['city']}「{weather}」{temp}℃，适合户外运动"
    plan = {
        "减脂": "有氧为主：快走/慢跑 30-40 分钟 + 力量训练 20 分钟",
        "增肌": "力量训练为主：胸背腿分化 + 少量有氧",
        "控糖": "中等强度有氧 30 分钟 + 抗阻训练",
        "维持健康": "每周 150 分钟中等强度运动（快走/骑行/游泳）",
    }.get(goal, "适量运动")
    return f"{venue}。\n🏃 锻炼建议（{goal}）：{plan}"


def _missing(profile: dict) -> list[str]:
    return [f for f, _ in _REPORT_FIELDS if not profile.get(f)]


def _next_question(profile: dict) -> str | None:
    m = _missing(profile)
    return dict(_REPORT_FIELDS)[m[0]] if m else None


def _absorb_answer(profile: dict, field: str | None, message: str) -> None:
    """把用户这句话当作对当前缺失字段的回答（裸答案兜底）。"""
    if not field:
        return
    if field == "sex":
        if "女" in message:
            profile["sex"] = "女"
        elif "男" in message:
            profile["sex"] = "男"
    elif field in ("age", "height_cm", "weight_kg"):
        m = re.search(r"(\d+(?:\.\d+)?)", message)
        if m:
            v = float(m.group(1))
            profile[field] = int(v) if field == "age" else v
    elif field == "goal":
        for g in ("减脂", "增肌", "维持健康", "控糖"):
            if g in message:
                profile["goal"] = g
                break


async def _report(profile: dict) -> str:
    """生成一天的饮食 + 锻炼报告。"""
    from .graph import workflow
    p = _profile(profile)
    params = {**p, "city": profile.get("city", "北京"),
              "restrictions": profile.get("restrictions", []),
              "location": profile.get("location")}
    r = await workflow.run_plan(params)
    rep = r["report"]
    storage.save_latest("plan", rep.get("meals", []))
    storage.save_latest("markets", rep.get("shopping", {}).get("markets", []))
    t = rep.get("targets", {})
    meals = "\n".join(
        f"{m['slot']}：" + "、".join(f"{i['food']}({i['cooking']})" for i in m['items'])
        for m in rep.get("meals", [])
    )
    mkts = "、".join(x["name"] for x in rep.get("shopping", {}).get("markets", [])[:3])
    ex = _exercise_advice(profile)
    return (f"📋 你的一天饮食锻炼报告\n\n"
            f"🎯 营养目标：约 {t.get('calories')} 千卡 · 蛋白 {t.get('protein_g')}g · 脂肪 {t.get('fat_g')}g · 碳水 {t.get('carb_g')}g\n\n"
            f"🍽️ 三餐（含做法）：\n{meals}\n\n"
            f"{ex}\n\n"
            f"🛒 附近采购：{mkts or '未找到'}\n\n"
            f"💡 小结：{rep.get('summary', '')}")


async def _capability(intent: str, profile: dict) -> str:
    from .graph import workflow
    p = _profile(profile)

    if intent == "goal":
        r = await workflow.run_goal(p)
        t = r["report"]["targets"]
        return (f"根据你的情况（{p['sex']} {p['height_cm']}cm {p['weight_kg']}kg {p['goal']}）："
                f"每日热量约 {t['calories']} 千卡，蛋白质 {t['protein_g']}g，脂肪 {t['fat_g']}g，碳水 {t['carb_g']}g。")

    if intent in ("meal_plan", "plan_all"):
        params = {**p, "city": profile.get("city", "北京"),
                  "restrictions": profile.get("restrictions", []),
                  "location": profile.get("location")}
        r = await workflow.run_plan(params)
        rep = r["report"]
        storage.save_latest("plan", rep.get("meals", []))
        storage.save_latest("markets", rep.get("shopping", {}).get("markets", []))
        meals = "\n".join(
            f"{m['slot']}：" + "、".join(f"{i['food']}({i['cooking']})" for i in m['items'])
            for m in rep.get("meals", [])
        )
        mkts = "、".join(x["name"] for x in rep.get("shopping", {}).get("markets", [])[:3])
        return f"{rep.get('summary', '')}\n\n🍽️ 三餐：\n{meals}\n\n🛒 附近采购：{mkts or '未找到'}"

    if intent == "where_to_eat":
        r = await workflow.run_where_to_eat({"city": profile.get("city", "北京"),
                                             "location": profile.get("location")})
        rep = r["report"]
        storage.save_latest("markets", rep.get("restaurants", []))
        mkts = "、".join(x["name"] for x in rep.get("restaurants", [])[:3])
        return f"附近可去的采购点：{mkts or '未找到，可换个城市试试'}"

    return ""


def _parse_food_items(text: str) -> list[dict]:
    """从「米饭200克、鸡胸肉150克」里解析食物+克数。"""
    parts = re.split(r"[、，,。;；]", text)
    items = []
    for p in parts:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(克|g|斤|两|公斤|kg|毫升|ml)", p, re.I)
        if not m:
            continue
        grams = float(m.group(1))
        unit = m.group(2).lower()
        if unit == "斤":
            grams *= 500
        elif unit == "两":
            grams *= 50
        elif unit in ("公斤", "kg"):
            grams *= 1000
        name = p[:m.start()].strip()
        name = re.sub(r"^(?:我|今天|昨天|早上|中午|晚上|吃了|喝了|还|又|大概|大约|了)+", "", name).strip()
        if name and grams > 0:
            items.append({"name": name, "grams": grams})
    return items


def _diet_log(message: str) -> str:
    from datetime import date
    from .data import food_db
    items = _parse_food_items(message)
    if not items:
        return "没能识别出食物，请用「食物名+克数」格式，比如：米饭200克、鸡胸肉150克。"
    df = food_db.load_db()
    total = {"energy_kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0, "fiber_g": 0, "sodium_mg": 0}
    lines = []
    for it in items:
        row = food_db.find_food(df, it["name"])
        if row is None:
            lines.append(f"{it['name']}（未识别）")
            continue
        n = food_db.nutrition(row, it["grams"])
        for k in total:
            total[k] += n.get(k, 0)
        lines.append(f"{row['food_name']} {it['grams']:.0f}克")
    if total["energy_kcal"] <= 0:
        return "这些食物我都没在食物库里识别出来，换个说法试试。"
    storage.save_diet_log("default", date.today().isoformat(), items,
                          {k: round(v, 1) for k, v in total.items()})
    return (f"已记录今日摄入：约 {total['energy_kcal']:.0f} 千卡，蛋白质 {total['protein_g']:.0f}g，"
            f"脂肪 {total['fat_g']:.0f}g，碳水 {total['carb_g']:.0f}g。\n（{'、'.join(lines)}）")


def _converse(message: str, history: list, llm) -> str:
    context = "\n".join(
        ("用户" if m["role"] == "user" else "助手") + "：" + m["content"]
        for m in history
    )
    prompt = ("以下是之前的对话（可能为空）：\n" + context +
              "\n\n现在用户说：" + message +
              "\n\n请用中文简洁友好地回答（120 字以内）。")
    try:
        reply = llm.complete(prompt, SYSTEM)
    except Exception:
        reply = ""
    return reply or "抱歉，我暂时没法回答，可以换个说法。"
