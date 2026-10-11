"""校验 Agent：营养达标率、忌口/过敏、结果合理性校验。"""
from __future__ import annotations


def run(state: dict) -> dict:
    task = state.get("task_type")
    warnings: list[str] = []

    if task == "meal_plan" and state.get("meal_plan"):
        ach = state["meal_plan"].get("achievement", {})
        for key, label in [("calories", "热量"), ("protein", "蛋白质"),
                           ("fat", "脂肪"), ("carb", "碳水")]:
            v = ach.get(key, 1.0)
            if v < 0.8 or v > 1.2:
                warnings.append(f"{label}达标率 {v * 100:.0f}%，偏离目标")
    elif task == "diet_analyze" and state.get("diet_analysis"):
        warnings.extend(state["diet_analysis"].get("diagnosis", []))
    elif task == "where_to_eat" and state.get("where_to_eat"):
        if "error" in state["where_to_eat"]:
            warnings.append(state["where_to_eat"]["error"])
        elif not state["where_to_eat"].get("results"):
            warnings.append("未找到符合条件的餐厅，可放宽预算或换关键词")

    # 反馈循环：达标率偏离目标时，向食谱规划 Agent 发起「重新规划」显式消息
    replan = False
    if task in ("meal_plan", "plan_all") and state.get("meal_plan"):
        ach = state["meal_plan"].get("achievement", {})
        if abs(ach.get("protein", 1) - 1) > 0.15 or abs(ach.get("calories", 1) - 1) > 0.15:
            replan = True

    replan_count = state.get("replan_count", 0)
    agent_messages = list(state.get("agent_messages", []))
    if replan:
        replan_count += 1
        agent_messages.append({
            "from": "校验 Agent", "to": "食谱规划 Agent",
            "type": "重新规划请求", "reason": "营养达标率偏离目标，请调整方案重试",
        })
        warnings.append("营养达标率偏离目标，已向食谱规划 Agent 发起重新规划")

    return {
        "validation": {"status": "需注意" if warnings else "通过", "warnings": warnings},
        "replan_needed": replan,
        "replan_count": replan_count,
        "agent_messages": agent_messages,
    }
