"""LangGraph 多 Agent 编排。

流程（按意图分流）：
    router -> goal      -> profile -> report
           -> meal_plan -> profile -> meal_planner -> rag -> validate -> report
           -> diet_analyze -> diet_analyzer -> rag -> validate -> report
           -> where_to_eat -> amap -> validate -> report
           -> query     -> rag -> report
"""
from __future__ import annotations

import time
import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .. import config
from ..agents import (
    amap_agent,
    diet_analyzer_agent,
    meal_planner_agent,
    profile_agent,
    rag_retrieval,
    reporter,
    router,
    validator,
)
from ..trace import tracer
from .. import llm as _llm
from ..data import storage as _storage


class AgentState(TypedDict, total=False):
    query: str
    task_type: str
    entities: dict
    profile: dict
    targets: dict
    meal_plan: dict
    diet_analysis: dict
    where_to_eat: dict
    sources: list
    rag_answer: str
    validation: dict
    report: dict
    trace_id: str
    llm_backend: str
    error: str
    replan_count: int
    replan_needed: bool
    agent_messages: list


def _n_router(s): return router.run(s)
def _n_profile(s): return profile_agent.run(s)
def _n_meal_planner(s): return meal_planner_agent.run(s)
def _n_diet_analyzer(s): return diet_analyzer_agent.run(s)
async def _n_amap(s): return await amap_agent.run(s)
def _n_rag(s): return rag_retrieval.run(s)
def _n_validate(s): return validator.run(s)
def _n_report(s): return reporter.run(s)


MAX_REPLAN = 1


def _after_router(state: AgentState):
    t = state.get("task_type")
    if t in ("goal", "meal_plan", "plan_all"):
        return "profile"
    if t == "diet_analyze":
        return ["diet_analyzer", "rag"]  # 并行
    if t == "where_to_eat":
        return "amap"
    return "rag"


def _after_profile(state: AgentState):
    t = state.get("task_type")
    if t == "goal":
        return "report"
    if t == "meal_plan":
        return ["meal_planner", "rag"]  # 并行
    if t == "plan_all":
        return ["meal_planner", "rag", "amap"]  # 并行
    return "report"


def _after_validate(state: AgentState):
    # 反馈循环：校验不达标时向食谱规划 Agent 发起重新规划（显式通信）
    if state.get("replan_needed") and state.get("replan_count", 0) <= MAX_REPLAN:
        return "meal_planner"
    return "report"


def _after_amap(state: AgentState):
    return "validate"


def _after_rag(state: AgentState):
    # query 直接出报告；其它任务先汇合到 validate（避免 report 多入边导致重复执行）
    return "report" if state.get("task_type") == "query" else "validate"


_graph = None


def build_graph():
    global _graph
    if _graph is not None:
        return _graph
    g = StateGraph(AgentState)
    for name, fn in [
        ("router", _n_router), ("profile", _n_profile),
        ("meal_planner", _n_meal_planner), ("diet_analyzer", _n_diet_analyzer),
        ("amap", _n_amap), ("rag", _n_rag), ("validate", _n_validate),
        ("report", _n_report),
    ]:
        g.add_node(name, fn)

    g.add_edge(START, "router")
    g.add_conditional_edges("router", _after_router)
    g.add_conditional_edges("profile", _after_profile)
    g.add_edge("meal_planner", "validate")
    g.add_edge("diet_analyzer", "validate")
    g.add_conditional_edges("validate", _after_validate)
    g.add_conditional_edges("amap", _after_amap)
    g.add_conditional_edges("rag", _after_rag)
    g.add_edge("report", END)

    _graph = g.compile()
    return _graph


def _new_trace_id() -> str:
    return f"{int(time.time())}-{uuid.uuid4().hex[:8]}"


async def invoke(initial_state: dict) -> dict:
    state = dict(initial_state)
    state.setdefault("trace_id", _new_trace_id())
    out = await build_graph().ainvoke(state)
    try:
        tracer.record(out)
    except Exception:
        pass
    return out


def _public(out: dict) -> dict:
    return {
        "trace_id": out.get("trace_id"),
        "task_type": out.get("task_type"),
        "llm_backend": out.get("llm_backend"),
        "report": out.get("report", {}),
    }


async def run_goal(profile: dict) -> dict:
    return _public(await invoke({"task_type": "goal", "entities": dict(profile)}))


async def run_meal_plan(profile: dict, restrictions: list[str] | None = None, seed=None) -> dict:
    entities = dict(profile)
    entities["restrictions"] = restrictions or []
    if seed is not None:
        entities["seed"] = seed
    return _public(await invoke({"task_type": "meal_plan", "entities": entities}))


async def run_diet_analyze(items: list[dict], profile: dict | None = None) -> dict:
    entities = {"items": items}
    if profile:
        entities.update(profile)
    return _public(await invoke({"task_type": "diet_analyze", "entities": entities}))


async def run_where_to_eat(params: dict) -> dict:
    return _public(await invoke({"task_type": "where_to_eat", "entities": dict(params)}))


async def run_plan(params: dict) -> dict:
    """综合方案：一个请求让 画像→食谱→校验→去哪吃→报告 多个 Agent 协作。"""
    return _public(await invoke({"task_type": "plan_all", "entities": dict(params)}))


async def run_query(question: str) -> dict:
    return _public(await invoke({"query": question}))


_PLAN_ALL_SEQUENCE = ["router", "profile", "meal_planner", "rag", "validate", "amap", "report"]


async def stream_plan(params: dict):
    """SSE 事件流：逐节点产出进度事件，供前端实时展示工作流执行到哪一步。"""
    state = {"task_type": "plan_all", "entities": dict(params),
             "trace_id": _new_trace_id()}
    yield {"event": "start", "task_type": "plan_all", "trace_id": state["trace_id"]}

    graph = build_graph()
    try:
        async for chunk in graph.astream(state, stream_mode="updates"):
            for node, update in chunk.items():
                state.update(update)
                yield {"event": "node_done", "node": node}
        try:
            tracer.record(state)
        except Exception:
            pass
        yield {"event": "result", "result": _public(state)}
    except Exception as e:
        yield {"event": "error", "message": str(e)}


_NODE_LABELS = {
    "router": "智能路由", "profile": "画像目标", "meal_planner": "食谱规划",
    "rag": "知识召回", "validate": "校验", "amap": "附近采购", "report": "报告生成",
}


def _meals_summary(mp):
    if not mp:
        return None
    return {
        "totals": mp.get("totals"),
        "achievement": mp.get("achievement"),
        "meals": [{"slot": m.get("slot"), "items": [{"food": i.get("food"), "grams": i.get("grams")} for i in m.get("items", [])]} for m in mp.get("meals", [])],
    }


def _step_io(node, prev, cur):
    inp, out, nar = {}, {}, ""
    if node == "router":
        inp = {"用户输入": prev.get("query") or "表单参数"}
        out = {"识别意图": cur.get("task_type")}
        nar = "识别为「综合方案」任务"
    elif node == "profile":
        e = prev.get("entities") or {}
        t = cur.get("targets") or {}
        inp = {"身高": e.get("height_cm"), "体重": e.get("weight_kg"), "目标": e.get("goal")}
        out = {"每日热量": t.get("calories"), "蛋白质": t.get("protein_g"), "脂肪": t.get("fat_g"), "碳水": t.get("carb_g")}
        nar = f"算出每天约 {t.get('calories')} 千卡"
    elif node == "meal_planner":
        inp = {"热量目标": (prev.get("targets") or {}).get("calories"), "忌口": (prev.get("entities") or {}).get("restrictions")}
        mp = cur.get("meal_plan") or {}
        meals = mp.get("meals", [])
        out = {"三餐": [f"{m.get('slot')}：" + "、".join(i.get('food') for i in m.get('items', [])) for m in meals]}
        nar = f"搭配出 {len(meals)} 餐，并附烹饪方式"
    elif node == "rag":
        out = {"召回片段": [s.get("title") for s in cur.get("sources", [])[:3]]}
        nar = "检索到膳食指南相关片段"
    elif node == "validate":
        inp = {"三餐热量": (prev.get("meal_plan") or {}).get("totals", {}).get("energy_kcal")}
        v = cur.get("validation") or {}
        out = {"结论": v.get("status"), "提示": v.get("warnings")}
        nar = "校验" + (v.get("status") or "通过")
        if cur.get("agent_messages"):
            out["发出的消息"] = cur.get("agent_messages")
    elif node == "amap":
        inp = {"城市": (prev.get("entities") or {}).get("city")}
        wt = cur.get("where_to_eat") or {}
        out = {"采购点": [r.get("name") for r in wt.get("results", [])[:3]]}
        nar = f"找到 {wt.get('total_matched')} 个附近采购点"
    elif node == "report":
        inp = {"目标热量": (prev.get("targets") or {}).get("calories"), "三餐合计": (prev.get("meal_plan") or {}).get("totals", {}).get("energy_kcal")}
        out = {"方案标题": (cur.get("report") or {}).get("title")}
        nar = "生成完整方案"
    return inp, out, nar


def _node_tools(node, cur):
    if node == "router":
        return ["大模型理解你想做什么", "规则提取身高体重等信息"]
    if node == "profile":
        return ["按 Mifflin-St Jeor 公式算热量"]
    if node == "meal_planner":
        return ["从 4857 种真实食物里搭配", "自动配烹饪方式"]
    if node == "rag":
        return ["关键词 + 语义混合检索膳食指南"]
    if node == "validate":
        return ["检查热量蛋白质是否达标", "检查忌口/过敏"]
    if node == "amap":
        wt = cur.get("where_to_eat") or {}
        return [f"高德地图搜「{wt.get('city')}」附近超市/菜市场"]
    if node == "report":
        return ["大模型把结果串成一段话"]
    return []


async def plan_steps(params: dict) -> dict:
    """运行完整流程，逐节点记录 输入/输出/工具调用/并行层，供前端单步调试。"""
    state = {"task_type": "plan_all", "entities": dict(params), "trace_id": _new_trace_id()}
    steps = []
    layers = []
    graph = build_graph()
    layer = 0
    tok_before = _llm.token_snapshot()
    t0 = time.time()
    prev = t0
    async for chunk in graph.astream(state, stream_mode="updates"):
        now = time.time()
        layers.append({"layer": layer, "nodes": list(chunk.keys()),
                       "duration_ms": round((now - prev) * 1000, 1)})
        prev = now
        pre = dict(state)  # 本超步之前的完整状态（并行节点共享同一 pre）
        for node, delta in chunk.items():
            after = {**pre, **delta}
            inp, out, nar = _step_io(node, pre, after)
            steps.append({
                "node": node, "label": _NODE_LABELS.get(node, node),
                "input": inp, "output": out, "tools": _node_tools(node, after),
                "narration": nar, "layer": layer,
            })
        for delta in chunk.values():
            state.update(delta)
        layer += 1
    total_ms = (time.time() - t0) * 1000
    tok_after = _llm.token_snapshot()
    try:
        tracer.record(state)
        _storage.save_trace(state["trace_id"], "plan_all", total_ms,
                            tok_after["prompt"] - tok_before["prompt"],
                            tok_after["completion"] - tok_before["completion"], layers)
    except Exception:
        pass
    # 去重：相邻重复节点保留首个
    deduped = []
    for st in steps:
        if deduped and deduped[-1]["node"] == st["node"]:
            continue
        deduped.append(st)
    return {"steps": deduped, "result": _public(state)}
