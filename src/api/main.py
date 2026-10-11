"""FastAPI 服务入口。

启动：python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from .. import chat, config
from ..graph.workflow import (
    plan_steps, run_diet_analyze, run_goal, run_meal_plan, run_plan, run_query,
    run_where_to_eat, stream_plan,
)
from ..trace import tracer
from . import schemas

config.load_env()

app = FastAPI(title="食策 · 个性化饮食规划智能体", version="1.0.0")
WEB_DIR = config.ROOT / "web"


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "diet-advisor-agent"}


@app.post("/api/goal")
async def goal(req: schemas.Profile) -> dict:
    return await run_goal(req.model_dump())


@app.post("/api/meal-plan")
async def meal_plan(req: schemas.MealPlanRequest) -> dict:
    data = req.model_dump()
    restrictions = data.pop("restrictions", None) or []
    seed = data.pop("seed", None)
    return await run_meal_plan(data, restrictions, seed)


@app.post("/api/analyze")
async def analyze(req: schemas.AnalyzeRequest) -> dict:
    data = req.model_dump()
    items = [{"name": it["name"], "grams": it["grams"]} for it in data.pop("items")]
    profile = {k: v for k, v in data.items() if v is not None}
    return await run_diet_analyze(items, profile)


@app.post("/api/plan")
async def plan(req: schemas.PlanRequest) -> dict:
    return await run_plan(req.model_dump())


@app.post("/api/plan/steps")
async def plan_steps_endpoint(req: schemas.PlanRequest) -> dict:
    """返回逐节点的输入/输出/工具调用快照，供前端单步调试。"""
    return await plan_steps(req.model_dump())


@app.post("/api/plan/stream")
async def plan_stream(req: schemas.PlanRequest) -> StreamingResponse:
    """SSE 流式：逐节点推送工作流进度。"""

    async def gen():
        async for evt in stream_plan(req.model_dump()):
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/where-to-eat")
async def where_to_eat(req: schemas.WhereToEatRequest) -> dict:
    return await run_where_to_eat(req.model_dump())


@app.post("/api/query")
async def query(req: schemas.QueryRequest) -> dict:
    return await run_query(req.question)


@app.post("/api/chat")
async def chat_endpoint(req: schemas.ChatRequest) -> dict:
    """多轮对话：返回回复 + session_id（用于记忆），自动路由到多 Agent 能力。"""
    return await chat.chat(req.message, req.session_id, req.location, req.city)


@app.post("/api/dashboard")
async def dashboard(req: schemas.DashboardRequest) -> dict:
    """营养仪表盘：返回每日营养目标 + 今日已摄入。"""
    from ..data import storage
    profile = {"sex": req.sex, "age": req.age, "height_cm": req.height_cm,
               "weight_kg": req.weight_kg, "activity": req.activity, "goal": req.goal}
    r = await run_goal(profile)
    return {"targets": r["report"]["targets"],
            "intake": storage.get_today_intake("default"),
            "plan": storage.get_latest("plan"),
            "markets": storage.get_latest("markets")}


@app.get("/api/weather")
async def weather(city: str) -> dict:
    from ..tools import amap
    return amap.get_weather(city)


@app.get("/api/regeo")
async def regeo(location: str) -> dict:
    from ..tools import amap
    return amap.regeo(location)


@app.get("/api/trace/{trace_id}")
def get_trace(trace_id: str) -> dict:
    rec = tracer.find(trace_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return rec


@app.get("/api/observability")
def observability(limit: int = 30) -> dict:
    """可观测性：最近请求的耗时 / token / 成本 + 逐层耗时。"""
    from ..data import storage
    from .. import llm
    traces = storage.get_traces(limit)
    n = len(traces)
    total_prompt = sum(t["prompt_tokens"] for t in traces)
    total_completion = sum(t["completion_tokens"] for t in traces)
    avg_ms = sum(t["duration_ms"] for t in traces) / n if n else 0
    # DeepSeek 近似定价：输入 ¥1/百万 token，输出 ¥2/百万 token
    cost = (total_prompt * 1 + total_completion * 2) / 1_000_000
    return {
        "summary": {
            "请求数": n,
            "平均耗时_ms": round(avg_ms, 1),
            "总输入token": total_prompt,
            "总输出token": total_completion,
            "总成本_元": round(cost, 4),
        },
        "traces": traces,
        "reliability": llm.reliability_status(),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")
