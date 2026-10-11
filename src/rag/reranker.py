"""轻量重排：按目标/营养素/忌口/食物关键词命中微调得分。"""
from __future__ import annotations

_ENTITY_TERMS = {
    "goal": ["减脂", "增肌", "控糖", "维持", "热量", "体重"],
    "nutrient": ["蛋白质", "碳水", "脂肪", "膳食纤维", "钠", "维生素", "矿物质"],
    "restriction": ["素食", "海鲜", "坚果", "乳糖", "麸质", "大豆", "嘌呤", "低GI", "辣"],
    "food": ["谷类", "蔬菜", "水果", "肉", "鱼", "蛋", "奶", "豆", "全谷"],
}


def rerank(results: list[dict], query: str, top_k: int = 3, boost: float = 0.15) -> list[dict]:
    scored: list[tuple[float, dict]] = []
    for r in results:
        s = r["score"]
        for terms in _ENTITY_TERMS.values():
            for t in terms:
                if t in query and t in r["text"]:
                    s += boost
        scored.append((s, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for s, r in scored[:top_k]:
        rr = dict(r)
        rr["rerank_score"] = round(s, 4)
        out.append(rr)
    return out
