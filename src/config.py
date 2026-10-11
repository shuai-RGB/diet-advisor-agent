"""全局配置、路径与常量。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
ARTIFACT_DIR = DATA_DIR / "artifacts"
for _d in (RAW_DIR, KNOWLEDGE_DIR, ARTIFACT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

FOOD_DB_FILE = DATA_DIR / "food_db.csv"
KB_INDEX = ARTIFACT_DIR / "kb_index.joblib"
TRACE_FILE = ARTIFACT_DIR / "trace.jsonl"

# ---- 画像 ----
GOALS = ["减脂", "增肌", "控糖", "维持健康"]
ACTIVITY_LEVELS = {"久坐": 1.2, "轻度": 1.375, "中度": 1.55, "高强度": 1.725}

# 三餐热量分配（早/午/晚）
MEAL_SLOTS = ["早餐", "午餐", "晚餐"]
MEAL_SHARES = {"早餐": 0.30, "午餐": 0.40, "晚餐": 0.30}

# 常见忌口/过敏标签
RESTRICTIONS = [
    "不吃辣", "素食", "忌海鲜", "忌坚果", "忌乳糖",
    "忌麸质", "忌大豆", "低嘌呤", "低GI",
]

# 食物大类（与食物成分表第6版分类对齐，用于食谱结构）
STAPLE_CATS = ["谷类及其制品", "薯类淀粉及其制品"]
PROTEIN_CATS = ["畜肉类及其制品", "禽肉类及其制品", "鱼虾蟹贝类", "蛋类及其制品", "干豆类及其制品", "乳类及其制品"]
MAIN_PROTEIN_CATS = ["畜肉类及其制品", "禽肉类及其制品", "鱼虾蟹贝类", "蛋类及其制品", "干豆类及其制品"]
DAIRY_CATS = ["乳类及其制品"]
VEG_CATS = ["蔬菜类及其制品", "菌藻类"]
FRUIT_CATS = ["水果类及其制品"]
NUT_CATS = ["坚果种子类"]
FAT_CATS = ["植物油", "动物油脂类"]


def load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=True)
    except Exception:
        pass


def get_amap_key() -> str:
    load_env()
    import os
    return os.getenv("AMAP_KEY", "").strip()
