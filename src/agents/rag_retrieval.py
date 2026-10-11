"""知识召回 Agent（RAG）：检索膳食指南与营养知识。"""
from __future__ import annotations

from ..llm import get_llm
from ..rag.retriever import load as load_retriever
from ..rag.reranker import rerank

_retriever = None


def _get_retriever():
    global _retriever
    if _retriever is None:
        _retriever = load_retriever()
    return _retriever


def _build_query(state: dict) -> str:
    ent = state.get("entities", {})
    parts = []
    if ent.get("goal"):
        parts.append(str(ent["goal"]))
    if ent.get("restrictions"):
        parts.extend(str(r) for r in ent["restrictions"])
    base = " ".join(parts) if parts else state.get("query", "")
    return f"{base} 饮食 营养"


def run(state: dict) -> dict:
    llm = get_llm()
    q = state.get("query") or _build_query(state)
    retriever = _get_retriever()
    results = retriever.search(q, k=8)
    results = rerank(results, q, top_k=4)
    out = {"sources": results}
    if state.get("task_type") == "query":
        out["rag_answer"] = _answer(q, results, llm)
    return out


def _answer(q: str, results: list[dict], llm) -> str:
    if not results:
        return "知识库中暂未检索到相关内容，请换个问法。"
    texts = [r["text"] for r in results]
    prompt = (
        "你是营养健康助手。请严格依据下方「知识库片段」回答用户问题，"
        "不要编造片段中不存在的信息；若片段不足以回答，请直接回复"
        "“知识库中暂无该问题的详细说明”。用中文回答，控制在 120 字以内。\n\n"
        f"用户问题：{q}\n\n知识库片段：\n" + "\n---\n".join(texts)
    )
    try:
        out = llm.complete(prompt)
        if out:
            return out
    except Exception:
        pass
    return "根据知识库：" + "；".join(t[:120] for t in texts[:2])
