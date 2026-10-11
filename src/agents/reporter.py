"""报告生成 Agent：按意图生成结构化报告 + 人类可读摘要。"""
from __future__ import annotations

from ..llm import get_llm


def run(state: dict) -> dict:
    llm = get_llm()
    task = state.get("task_type")

    if task == "goal":
        report = _goal_report(state, llm)
    elif task == "plan_all":
        report = _plan_report(state, llm)
    elif task == "meal_plan":
        report = _meal_report(state, llm)
    elif task == "diet_analyze":
        report = _analyze_report(state, llm)
    elif task == "where_to_eat":
        report = _eat_report(state, llm)
    else:
        report = {
            "title": "营养知识问答",
            "answer": state.get("rag_answer", ""),
            "sources": _source_refs(state),
        }
    return {"report": report}


def _source_refs(state: dict) -> list[dict]:
    return [{"id": s["id"], "doc": s["doc"], "title": s["title"]}
            for s in state.get("sources", [])]


def _goal_report(state, llm) -> dict:
    t = state.get("targets", {})
    prompt = (
        "你是营养师。根据以下营养目标，用中文给出一段 60~90 字的实用建议。\n"
        f"目标：{t}"
    )
    summary = _llm_or(llm, prompt, _goal_summary(t))
    return {"title": "每日营养目标", "targets": t, "summary": summary}


def _goal_summary(t: dict) -> str:
    return (
        f"你的 BMI 为 {t.get('bmi')}，基础代谢约 {t.get('bmr')} 千卡。"
        f"每日建议摄入 {t.get('calories')} 千卡，蛋白质 {t.get('protein_g')} 克、"
        f"脂肪 {t.get('fat_g')} 克、碳水 {t.get('carb_g')} 克，膳食纤维约 25 克，钠 <2000 毫克。"
    )


def _meal_report(state, llm) -> dict:
    mp = state.get("meal_plan", {})
    prompt = (
        "你是营养师。根据以下一日三餐方案与达标率，用中文给一段 80~120 字的点评与调整建议。\n"
        f"方案：{mp}"
    )
    summary = _llm_or(llm, prompt, _meal_summary(mp))
    return {
        "title": "一日三餐食谱",
        "targets": mp.get("targets"),
        "meals": mp.get("meals"),
        "totals": mp.get("totals"),
        "achievement": mp.get("achievement"),
        "restrictions_applied": mp.get("restrictions_applied"),
        "sources": _source_refs(state),
        "summary": summary,
    }


def _meal_summary(mp: dict) -> str:
    t = mp.get("totals", {})
    ach = mp.get("achievement", {})
    return (
        f"本方案全天约 {t.get('energy_kcal', 0):.0f} 千卡，蛋白质 {t.get('protein_g', 0):.0f} 克、"
        f"脂肪 {t.get('fat_g', 0):.0f} 克、碳水 {t.get('carb_g', 0):.0f} 克。"
        f"热量达标率 {ach.get('calories', 0) * 100:.0f}%。"
    )


def _analyze_report(state, llm) -> dict:
    da = state.get("diet_analysis", {})
    prompt = (
        "你是营养师。根据以下饮食分析结果，用中文给出 60~90 字诊断与改进建议。\n"
        f"分析：{da}"
    )
    summary = _llm_or(llm, prompt, _analyze_summary(da))
    return {"title": "饮食分析", "totals": da.get("totals"),
            "items": da.get("items"), "targets": da.get("targets"),
            "diagnosis": da.get("diagnosis"), "summary": summary}


def _analyze_summary(da: dict) -> str:
    t = da.get("totals", {})
    d = da.get("diagnosis", [])
    base = f"本次共摄入约 {t.get('energy_kcal', 0):.0f} 千卡。"
    return base + ("；".join(d) if d else "整体在合理范围。")


def _plan_report(state, llm) -> dict:
    """综合方案：汇总画像目标 + 三餐 + 外出就餐 + 校验 + 依据。"""
    t = state.get("targets", {})
    mp = state.get("meal_plan", {})
    wt = state.get("where_to_eat", {})
    v = state.get("validation", {})
    prompt = (
        "你是营养师。把下面这套方案串成一段连贯的总结（120~160 字）：先说每日目标，"
        "再说三餐如何围绕目标安排（达标情况、烹饪方式），最后说附近去哪个超市/菜市场买菜，"
        "并点明 1 个注意事项。\n"
        f"目标：{t}\n三餐合计：{mp.get('totals')}（达标率 {mp.get('achievement')}）\n"
        f"附近采购：{wt.get('city')} 的 {wt.get('results', [])[:3]}\n校验：{v}"
    )
    summary = _llm_or(llm, prompt, _plan_summary(t, mp, wt))
    return {
        "title": "个性化饮食综合方案",
        "targets": t,
        "meals": mp.get("meals"),
        "meal_totals": mp.get("totals"),
        "achievement": mp.get("achievement"),
        "shopping": {
            "city": wt.get("city"), "keywords": wt.get("keywords"),
            "markets": wt.get("results", [])[:5],
        },
        "validation": v,
        "sources": _source_refs(state),
        "summary": summary,
    }


def _plan_summary(t, mp, wt) -> str:
    return (
        f"你的目标是每日约 {t.get('calories')} 千卡（蛋白质 {t.get('protein_g')} 克）。"
        f"三餐方案合计约 {mp.get('totals', {}).get('energy_kcal', 0):.0f} 千卡；"
        f"附近可去「{wt.get('keywords')}」采购食材。"
    )


def _eat_report(state, llm) -> dict:
    wt = state.get("where_to_eat", {})
    results = wt.get("results", [])
    prompt = (
        "你是美食推荐助手。根据以下餐厅列表，用中文给一段 80~120 字的推荐说明，"
        "点明 1~2 家最值得去的店及理由。\n"
        f"餐厅：{results[:5]}"
    )
    summary = _llm_or(llm, prompt, _eat_summary(results))
    return {
        "title": "去哪吃推荐",
        "city": wt.get("city"), "keywords": wt.get("keywords"),
        "budget": wt.get("budget"), "restrictions": wt.get("restrictions"),
        "total_matched": wt.get("total_matched"),
        "restaurants": results,
        "summary": summary,
    }


def _eat_summary(results: list[dict]) -> str:
    if not results:
        return "未找到符合条件的餐厅。"
    top = results[0]
    return f"推荐「{top.get('name')}」（{top.get('district', '')}，评分 {top.get('rating') or '-'}，人均 {top.get('cost') or '-'} 元）。"


def _llm_or(llm, prompt: str, fallback: str) -> str:
    try:
        out = llm.complete(prompt)
        if out:
            return out
    except Exception:
        pass
    return fallback
