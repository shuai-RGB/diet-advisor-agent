"""高德地图 Web 服务 API 客户端（「附近采购」工具调用）。"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .. import config
from ..reliability import retry


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@retry(max_attempts=3, base_delay=0.5)
def _fetch_json(url: str, timeout: int = 15) -> dict:
    """带重试的高德接口请求。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def search_pois(city: str, keywords: str, budget: float | None = None,
                offset: int = 15) -> dict:
    key = config.get_amap_key()
    if not key:
        return {"error": "未配置高德地图 AMAP_KEY，无法查询附近超市/菜市场"}

    params = {
        "key": key, "keywords": keywords, "city": city,
        "output": "json", "offset": str(offset), "page": "1", "extensions": "all",
    }
    url = "https://restapi.amap.com/v3/place/text?" + urllib.parse.urlencode(params)
    try:
        data = _fetch_json(url)
    except Exception as e:
        return {"error": f"高德接口调用失败：{e}"}

    if data.get("status") != "1":
        return {"error": data.get("info", "高德接口返回异常")}

    pois = []
    for p in data.get("pois", []):
        biz = p.get("biz_ext") or {}
        pois.append({
            "name": p.get("name"),
            "address": p.get("address"),
            "district": p.get("adname"),
            "location": p.get("location"),
            "type": p.get("type"),
            "cost": _f(biz.get("cost")),
            "rating": _f(biz.get("rating")),
            "tel": p.get("tel"),
            "tags": [t for t in (p.get("atag") or "").split(",") if t][:8],
        })
    return {"count": data.get("count"), "pois": pois}


def search_around(location: str, keywords: str, radius: int = 5000, offset: int = 15) -> dict:
    """高德周边搜索：按用户经纬度搜附近 POI，自带距离（米）。"""
    key = config.get_amap_key()
    if not key:
        return {"error": "未配置高德地图 AMAP_KEY"}
    params = {"key": key, "location": location, "keywords": keywords,
              "radius": str(radius), "offset": str(offset), "page": "1", "extensions": "all"}
    url = "https://restapi.amap.com/v3/place/around?" + urllib.parse.urlencode(params)
    try:
        data = _fetch_json(url)
    except Exception as e:
        return {"error": f"高德接口调用失败：{e}"}
    if data.get("status") != "1":
        return {"error": data.get("info", "高德接口返回异常")}
    pois = []
    for p in data.get("pois", []):
        biz = p.get("biz_ext") or {}
        pois.append({
            "name": p.get("name"), "address": p.get("address"),
            "district": p.get("adname"), "location": p.get("location"),
            "type": p.get("type"), "distance_m": p.get("distance"),
            "cost": _f(biz.get("cost")), "rating": _f(biz.get("rating")),
            "tel": p.get("tel"),
        })
    return {"count": data.get("count"), "pois": pois}


def get_weather(city: str) -> dict:
    """高德天气查询（实况）。"""
    key = config.get_amap_key()
    if not key:
        return {"error": "未配置高德地图 AMAP_KEY"}
    params = {"key": key, "city": city, "extensions": "base"}
    url = "https://restapi.amap.com/v3/weather/weatherInfo?" + urllib.parse.urlencode(params)
    try:
        data = _fetch_json(url)
    except Exception as e:
        return {"error": f"天气查询失败：{e}"}
    if data.get("status") != "1":
        return {"error": data.get("info", "天气接口异常")}
    lives = data.get("lives") or []
    if not lives:
        return {"error": "未查到该城市天气"}
    live = lives[0]
    return {
        "city": live.get("city"), "weather": live.get("weather"),
        "temperature": live.get("temperature"), "winddirection": live.get("winddirection"),
        "windpower": live.get("windpower"), "humidity": live.get("humidity"),
    }


def regeo(location: str) -> dict:
    """逆地理编码：经纬度 → 城市/区县/地址。"""
    key = config.get_amap_key()
    if not key:
        return {"error": "未配置高德地图 AMAP_KEY"}
    params = {"key": key, "location": location, "extensions": "base"}
    url = "https://restapi.amap.com/v3/geocode/regeo?" + urllib.parse.urlencode(params)
    try:
        data = _fetch_json(url)
    except Exception as e:
        return {"error": f"逆地理编码失败：{e}"}
    if data.get("status") != "1":
        return {"error": data.get("info", "逆地理编码异常")}
    geo = data.get("regeocode") or {}
    comp = geo.get("addressComponent") or {}
    return {"city": comp.get("city") or comp.get("province"),
            "district": comp.get("district"),
            "address": geo.get("formatted_address")}
