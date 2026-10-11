"""推理链路溯源：记录每次请求的输入、中间结果与结论，支持复核。"""
from __future__ import annotations

import datetime as _dt
import json

from .. import config


def record(state: dict, path=None) -> dict:
    rec = {
        "trace_id": state.get("trace_id"),
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "task_type": state.get("task_type"),
        "llm_backend": state.get("llm_backend"),
        "query": state.get("query"),
        "entities": state.get("entities"),
        "targets": state.get("targets"),
        "meal_plan_totals": (state.get("meal_plan") or {}).get("totals"),
        "meal_plan_achievement": (state.get("meal_plan") or {}).get("achievement"),
        "diet_analysis": (state.get("diet_analysis") or {}).get("totals"),
        "where_to_eat": {
            "city": (state.get("where_to_eat") or {}).get("city"),
            "keywords": (state.get("where_to_eat") or {}).get("keywords"),
            "total_matched": (state.get("where_to_eat") or {}).get("total_matched"),
        },
        "validation": state.get("validation"),
        "sources": [{"id": s.get("id"), "title": s.get("title")} for s in state.get("sources", [])],
    }
    p = path or config.TRACE_FILE
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def find(trace_id: str, path=None) -> dict | None:
    p = path or config.TRACE_FILE
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("trace_id") == trace_id:
                return rec
    return None
