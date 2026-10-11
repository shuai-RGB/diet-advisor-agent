"""「附近采购」工具调用 Agent：调高德地图 API 搜附近超市/菜市场（支持定位算距离）。"""
from __future__ import annotations

import asyncio

from ..tools import amap


async def run(state: dict) -> dict:
    ent = state.get("entities", {})
    city = ent.get("city", "北京")
    location = ent.get("location")
    # 搜超市 + 菜市场，合并去重
    all_pois = []
    for kw in ("超市", "菜市场"):
        if location:
            res = await asyncio.to_thread(amap.search_around, location, kw)
        else:
            res = await asyncio.to_thread(amap.search_pois, city, kw, None)
        if "error" not in res:
            all_pois.extend(res.get("pois", []))
    seen, pois = set(), []
    for p in all_pois:
        if p["name"] not in seen:
            seen.add(p["name"])
            pois.append(p)
    if location:
        pois.sort(key=lambda p: p.get("distance_m") or 999999)
    else:
        pois.sort(key=lambda p: (p.get("rating") or 0), reverse=True)
    return {"where_to_eat": {
        "city": city, "keywords": "超市/菜市场",
        "location": location, "total_matched": len(pois), "results": pois[:6],
    }}
