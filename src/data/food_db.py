"""食物营养数据库：加载《中国食物成分表(第6版)》、查询、忌口/过敏过滤。"""
from __future__ import annotations

import difflib

import pandas as pd

from .. import config

_db = None

# 口语名 -> 数据库规范名关键词（用户常输入 vs 食物成分表标准名）
ALIASES = {
    "米饭": "米饭", "大米饭": "米饭", "稀饭": "粥", "粥": "粥",
    "鸡胸肉": "鸡胸脯肉", "鸡胸": "鸡胸脯肉", "鸡腿肉": "鸡腿", "鸡腿": "鸡腿",
    "牛奶": "牛乳", "纯牛奶": "牛乳", "酸奶": "酸奶",
    "鸡蛋": "鸡蛋", "西红柿": "番茄", "番茄": "番茄",
    "西兰花": "西兰花", "西蓝花": "西兰花", "白菜": "白菜",
    "土豆": "马铃薯［土豆、洋芋］", "红薯": "甘薯（红心）［山芋、红薯］",
    "地瓜": "甘薯（红心）［山芋、红薯］", "山药": "山药",
    "三文鱼": "三文鱼", "虾": "虾", "牛肉": "牛肉", "猪肉": "猪肉", "羊肉": "羊肉",
    "燕麦": "燕麦", "玉米": "玉米", "豆腐": "豆腐", "豆浆": "豆浆",
    "橙子": "橙", "橙": "橙", "葡萄": "葡萄", "草莓": "草莓", "香蕉": "香蕉",
    "苹果": "苹果", "黄瓜": "黄瓜", "胡萝卜": "胡萝卜", "菠菜": "菠菜",
    "面条": "面条", "馒头": "馒头", "面包": "面包",
}


def load_db() -> pd.DataFrame:
    global _db
    if _db is None:
        _db = pd.read_csv(config.FOOD_DB_FILE)
    return _db


_PROCESSED_KW = ("粉", "淀粉", "干", "酱", "糊", "油", "糖", "膏", "蜜", "炼乳", "奶油", "脆", "酥")


def _pick(df: pd.DataFrame, mask) -> dict | None:
    """在命中的食物里优先选非加工品、再选名字最短的，返回记录。"""
    sub = df[mask]
    if sub.empty:
        return None
    sub = sub.copy()
    sub["_len"] = sub["food_name"].astype(str).str.len()
    sub["_proc"] = sub["food_name"].astype(str).str.contains("|".join(_PROCESSED_KW), regex=True, na=False)
    return sub.sort_values(["_proc", "_len"]).iloc[0].to_dict()


def find_food(df: pd.DataFrame, name: str) -> dict | None:
    """按名称查食物：同义词 -> 精确 -> 正向包含 -> 模糊匹配。"""
    name = name.strip()
    names = df["food_name"].astype(str)
    alias = ALIASES.get(name)
    if alias:
        r = _pick(df, names == alias)  # 精确优先
        if r:
            return r
        r = _pick(df, names.str.contains(alias, case=False, na=False, regex=False))
        if r:
            return r
    r = _pick(df, names == name)
    if r:
        return r
    r = _pick(df, names.str.contains(name, case=False, na=False, regex=False))
    if r:
        return r
    close = difflib.get_close_matches(name, names.tolist(), n=1, cutoff=0.5)
    if close:
        r = _pick(df, names == close[0])
        if r:
            return r
    return None


def nutrition(row: dict, grams: float) -> dict:
    """按克数计算某食物的营养成分。"""
    def f(col: str) -> float:
        return float(row.get(col, 0) or 0) * grams / 100.0
    return {
        "energy_kcal": round(f("energy_kcal"), 1),
        "protein_g": round(f("protein_g"), 1),
        "fat_g": round(f("fat_g"), 1),
        "carb_g": round(f("carb_g"), 1),
        "fiber_g": round(f("fiber_g"), 1),
        "sodium_mg": round(f("sodium_mg"), 1),
        "cholesterol_mg": round(f("cholesterol_mg"), 1),
    }


def violates(row: dict, restrictions: list[str]) -> bool:
    """判断食物是否违反用户的忌口/过敏。"""
    if not restrictions:
        return False
    name = str(row.get("food_name", ""))
    cat = str(row.get("category", ""))
    sub = str(row.get("subcategory", ""))
    for r in restrictions:
        if r == "素食" and cat in ("畜肉类及其制品", "禽肉类及其制品", "鱼虾蟹贝类", "蛋类及其制品"):
            return True
        if r == "忌海鲜" and cat == "鱼虾蟹贝类":
            return True
        if r == "忌乳糖" and cat == "乳类及其制品":
            return True
        if r == "忌坚果" and cat == "坚果种子类":
            return True
        if r == "忌大豆" and ("大豆" in sub or "豆腐" in name or "豆浆" in name or "黄豆" in name):
            return True
        if r == "忌麸质" and any(k in name for k in ("小麦", "面粉", "面包", "面条", "馒头")):
            return True
        if r == "不吃辣" and ("辣" in name or "辣椒" in name):
            return True
        if r == "低嘌呤" and cat in ("畜肉类及其制品", "禽肉类及其制品", "鱼虾蟹贝类"):
            return True
        if r == "低GI" and any(k in name for k in ("糖", "蜂蜜", "甜", "果酱")):
            return True
    return False


def filter_df(df: pd.DataFrame, restrictions: list[str]) -> pd.DataFrame:
    """向量化按忌口/过敏过滤食物库。"""
    if not restrictions:
        return df
    mask = pd.Series(True, index=df.index)
    cat = df["category"]
    name = df["food_name"].astype(str)
    for r in restrictions:
        if r == "素食":
            mask &= ~cat.isin(("畜肉类及其制品", "禽肉类及其制品", "鱼虾蟹贝类", "蛋类及其制品"))
        elif r == "忌海鲜":
            mask &= cat != "鱼虾蟹贝类"
        elif r == "忌乳糖":
            mask &= cat != "乳类及其制品"
        elif r == "忌坚果":
            mask &= cat != "坚果种子类"
        elif r == "忌大豆":
            mask &= ~name.str.contains("豆腐|豆浆|大豆|黄豆", regex=True, na=False)
        elif r == "忌麸质":
            mask &= ~name.str.contains("小麦|面粉|面包|面条|馒头", regex=True, na=False)
        elif r == "不吃辣":
            mask &= ~name.str.contains("辣|辣椒", regex=True, na=False)
        elif r == "低嘌呤":
            mask &= ~cat.isin(("畜肉类及其制品", "禽肉类及其制品", "鱼虾蟹贝类"))
        elif r == "低GI":
            mask &= ~name.str.contains("糖|蜂蜜|甜|果酱", regex=True, na=False)
    return df[mask]


def cooking_method(row: dict) -> str:
    """按食物类别给一个家常烹饪方式。"""
    cat = str(row.get("category", ""))
    if cat in ("水果类及其制品", "乳类及其制品", "坚果种子类"):
        return "直接食用"
    if cat == "蔬菜类及其制品":
        return "清炒"
    if cat == "菌藻类":
        return "凉拌/炖汤"
    if cat in ("畜肉类及其制品", "禽肉类及其制品"):
        return "炖/炒"
    if cat == "鱼虾蟹贝类":
        return "清蒸/红烧"
    if cat == "蛋类及其制品":
        return "水煮/蒸"
    if cat in ("谷类及其制品", "薯类淀粉及其制品"):
        return "蒸/煮"
    if cat == "干豆类及其制品":
        return "炖煮"
    return "清炒"


_COMMON = {
    "staple": ["米", "面", "馒头", "面包", "面条", "玉米", "红薯", "土豆", "燕麦", "粥", "粉条"],
    "protein": ["鸡胸", "鸡肉", "牛肉", "猪肉", "羊肉", "鱼", "虾", "三文鱼", "鳕鱼", "瘦"],
    "dairy": ["牛乳", "牛奶", "鲜奶", "酸奶"],
    "veg": ["白菜", "菠菜", "西兰花", "胡萝卜", "番茄", "黄瓜", "芹菜", "油菜", "生菜", "蘑菇", "海带", "青椒", "茄子", "豆角", "冬瓜", "南瓜"],
    "fruit": ["苹果", "香蕉", "橙", "梨", "葡萄", "草莓", "蓝莓", "桃", "西瓜", "猕猴桃", "柚子", "芒果"],
}


def pick_common(df: pd.DataFrame, cats: list[str], kind: str, n: int = 100) -> list[dict]:
    """从指定大类里挑常见食材（按关键词过滤），返回记录列表。"""
    kws = _COMMON[kind]
    sub = df[df["category"].isin(cats)]
    if sub.empty:
        sub = df
    mask = sub["food_name"].apply(lambda x: any(k in str(x) for k in kws))
    sel = sub[mask]
    if sel.empty:
        sel = sub
    return sel.head(n).to_dict("records")
