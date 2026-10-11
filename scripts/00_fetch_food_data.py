"""下载并合并《中国食物成分表标准版(第6版)》数据 -> data/food_db.csv

数据源：https://github.com/Sanotsu/china-food-composition-data
（真实公开数据，每 100g 可食部营养成分）
"""
import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

API_TREE = "https://api.github.com/repos/Sanotsu/china-food-composition-data/git/trees/main?recursive=1"
RAW = "https://raw.githubusercontent.com/Sanotsu/china-food-composition-data/main/"

STR_FIELDS = {"foodCode": "food_code", "foodName": "food_name"}
NUM_FIELDS = {
    "edible": "edible", "energyKCal": "energy_kcal", "protein": "protein_g",
    "fat": "fat_g", "CHO": "carb_g", "dietaryFiber": "fiber_g",
    "Na": "sodium_mg", "cholesterol": "cholesterol_mg",
}
_ZERO = {"Tr", "tr", "痕量", "微量", "未检出", "未测定"}


def _num(v):
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "—", "…", "-", "N/A", "NA"):
        return None
    if s in _ZERO:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return None


def main() -> None:
    tree = json.load(urllib.request.urlopen(API_TREE, timeout=60))
    paths = [t["path"] for t in tree["tree"]
             if t["path"].startswith("json_data_v3")
             and "merged_" in t["path"] and t["path"].endswith(".json")]

    rows = []
    for i, p in enumerate(paths):
        stem = Path(p).stem.replace("merged_", "")
        cat, _, sub = stem.partition("-")
        url = RAW + quote(p, safe="/")
        try:
            data = json.load(urllib.request.urlopen(url, timeout=60))
        except Exception as e:
            print(f"  skip {p}: {e}")
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            row = {"category": cat, "subcategory": sub}
            for src, dst in STR_FIELDS.items():
                row[dst] = str(item.get(src) or "").strip()
            for src, dst in NUM_FIELDS.items():
                row[dst] = _num(item.get(src))
            rows.append(row)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(paths)} files")

    import pandas as pd
    df = pd.DataFrame(rows)
    df = df.dropna(subset=["energy_kcal", "protein_g", "fat_g", "carb_g"])
    for c in ["fiber_g", "sodium_mg", "cholesterol_mg", "edible"]:
        df[c] = df[c].fillna(0).astype(float)

    out = ROOT / "data" / "food_db.csv"
    df.to_csv(out, index=False)
    print(f"done: {len(df)} foods -> {out}")
    print(df.groupby("category").size().to_string())


if __name__ == "__main__":
    main()
