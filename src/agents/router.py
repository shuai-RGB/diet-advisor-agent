"""调度/路由 Agent：识别意图并抽取实体。"""
from __future__ import annotations

import re

from .. import config
from ..llm import get_llm

_INTENT_RULES = [
    ("query", ["不能吃", "不能喝", "忌口", "能不能吃", "能不能喝"]),
    ("plan_all", ["方案", "综合", "一整套", "完整", "一站式", "整体", "帮我安排", "全套"]),
    ("report", ["报告", "饮食锻炼", "一日方案", "今天怎么安排", "一天怎么"]),
    ("where_to_eat", ["去哪吃", "吃什么店", "餐厅", "馆子", "附近", "外卖", "下馆子", "美食推荐", "好吃"]),
    ("weather", ["天气", "下雨", "下雪", "温度", "气温", "冷不冷", "热不热", "降温"]),
    ("exercise", ["锻炼", "运动", "健身", "跑步", "减肥运动", "拉伸"]),
    ("meal_plan", ["食谱", "菜单", "一日三餐", "三餐", "吃什么", "帮我配", "搭配", "规划"]),
    ("diet_analyze", ["分析", "我吃了", "我今天", "饮食记录"]),
    ("goal", ["算", "计算", "目标", "每天吃多少", "热量", "卡路里", "需要多少", "基础代谢", "摄入多少"]),
    ("query", ["什么是", "为什么", "怎么", "如何", "指南", "建议", "过敏"]),
]

_CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "武汉", "西安",
           "南京", "苏州", "天津", "长沙", "郑州", "青岛", "大连", "厦门", "福州",
           "宁波", "昆明", "合肥", "沈阳", "哈尔滨", "长春", "济南", "石家庄", "太原",
           "南昌", "贵阳", "南宁", "海口", "兰州", "乌鲁木齐", "呼和浩特", "银川",
           "西宁", "拉萨", "佛山", "东莞", "无锡", "温州", "常州", "珠海"]

_CUISINES = ["川菜", "粤菜", "湘菜", "火锅", "烧烤", "日料", "韩餐", "西餐", "面馆",
             "素食", "海鲜", "小吃", "东北菜", "江浙菜", "西北菜", "云南菜", "甜品", "咖啡"]


def classify(query: str, llm) -> str:
    # 规则优先（确定性），LLM 兜底（处理规则没覆盖的歧义表达）
    for intent, kws in _INTENT_RULES:
        if any(k in query for k in kws):
            return intent
    prompt = (
        "判断用户意图，只返回一个词：report / plan_all / goal / meal_plan / diet_analyze / where_to_eat / exercise / weather / query。\n"
        "report=想要一天的饮食锻炼报告（要问全信息）；plan_all=想要一套完整方案；goal=想算每日营养或热量目标；"
        "meal_plan=只想要一日三餐食谱；diet_analyze=分析已吃的食物；"
        "where_to_eat=想找附近超市菜市场/采购；exercise=想锻炼/运动建议；weather=想查天气；query=其它健康问题。\n"
        f"用户输入：{query}"
    )
    try:
        out = llm.complete(prompt).strip().lower()
        if out in ("report", "plan_all", "goal", "meal_plan", "diet_analyze", "where_to_eat", "exercise", "weather", "query"):
            return out
    except Exception:
        pass
    return "query"


def extract_entities(query: str) -> dict:
    ent: dict = {}
    if "女" in query:
        ent["sex"] = "女"
    elif "男" in query:
        ent["sex"] = "男"
    m = re.search(r"(\d{1,3})\s*岁", query)
    if m:
        ent["age"] = int(m.group(1))
    m = re.search(r"(\d{3})\s*(?:cm|厘米)", query)
    if m:
        ent["height_cm"] = float(m.group(1))
    m = re.search(r"(\d{2,3}(?:\.\d+)?)\s*(?:kg|公斤)", query)
    if m:
        ent["weight_kg"] = float(m.group(1))
    for g in config.GOALS:
        if g in query:
            ent["goal"] = g
            break
    for a in config.ACTIVITY_LEVELS:
        if a in query:
            ent["activity"] = a
            break
    restrictions = [r for r in config.RESTRICTIONS if r in query]
    if restrictions:
        ent["restrictions"] = restrictions
    for c in _CITIES:
        if c in query:
            ent["city"] = c
            break
    for c in _CUISINES:
        if c in query:
            ent["keywords"] = c
            break
    m = re.search(r"(?:人均|预算)\s*(\d+)", query)
    if m:
        ent["budget"] = float(m.group(1))
    return ent


def run(state: dict) -> dict:
    llm = get_llm()
    q = state.get("query", "")
    task = state.get("task_type")
    if not task:
        task = classify(q, llm)
    entities = state.get("entities") or {}
    if not entities and q:
        entities = extract_entities(q)
    return {"task_type": task, "entities": entities, "llm_backend": llm.name}
