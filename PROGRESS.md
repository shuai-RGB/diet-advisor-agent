# 开发进度快照（供新会话/新 AI 无缝接手）

## 项目定位（最终态）
「健康助手」：对话为核心入口（多轮记忆），多 Agent 协作，覆盖饮食、菜谱、营养、锻炼、天气、附近采购。
配营养仪表盘 + 饮食记录存储 + 监控页。流程图保留为右下角可缩放小窗口。

## 技术栈
- 后端：FastAPI + LangGraph（8 Agent 并行 DAG + 反馈循环）+ SQLite
- LLM：OpenAI 兼容（DeepSeek，.env 的 LLM_API_KEY），`llm.py` 带重试/熔断/降级/预算，无 key 自动切 RuleBasedLLM
- ReAct：`react_agent.py`，7 个工具（算目标/生成三餐/查天气/找超市/查知识/查食物/ask_user）
- RAG：BM25 + TF-IDF 混合检索（中文 bigram），语料 data/knowledge/*.md（当前偏少，待扩）
- 数据：4857 种真实食物（data/food_db.csv，中国食物成分表第6版）
- 工具：高德 API（POI 周边搜索/天气/逆地理编码，AMAP_KEY 在 .env）

## 全部完成（6 个升级项）
1. ✅ 评测体系（scripts/eval.py + data/eval/*.json，意图 45/45、食物 35/35、热量偏差 0.0%）
2. ✅ ReAct + 真 tool-calling（react_agent.py）
3. ✅ 可观测性（token/耗时/成本/熔断/预算 → /api/observability + 监控页）
4. ✅ 记忆个性化（memories 表 + get_preferences 从饮食记录学偏好）
5. ✅ 可靠性（reliability.py：重试/熔断/预算；LLM 挂了自动切规则引擎）
6. ✅ 并行 fan-out + 反馈循环（校验→重规划，显式消息）

验收：`python scripts/acceptance.py` → **14/14 通过**。

## 关键文件
- src/react_agent.py —— ReAct 引擎（SYSTEM + TOOLS + react_chat）
- src/chat.py —— 聊天入口（多轮记忆/画像记忆/追问/偏好记忆存储）
- src/llm.py —— LLM 可插拔 + 可靠性（token 计量、熔断、预算）
- src/reliability.py —— CircuitBreaker / TokenBudget / retry
- src/graph/workflow.py —— 编排 + plan_steps（逐层计时 + 存 trace）
- src/data/storage.py —— SQLite（chat_history/users/diet_logs/latest/traces/memories）
- src/data/{food_db,profile,meal_planner,diet_analyzer}.py
- src/tools/amap.py —— search_pois/search_around/get_weather/regeo
- src/rag/{corpus,retriever,reranker}.py
- src/api/{main,schemas}.py
- web/index.html —— 单文件前端（首页/聊天/监控/过程展示器）
- scripts/{smoke_test,benchmark,eval,acceptance}.py

## 启动
```
cd D:\workspace\mutiagent\diet-advisor-agent
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```
浏览器 http://127.0.0.1:8000

## 待办（可选）
- RAG 升级（向量检索 + rerank + 召回评测）
- 知识库扩充（当前 4 个 md 共约 2500 字，偏少）
- 首页加「你的偏好/爱吃的」展示

## 注意
- 食物口语名→规范名：food_db.ALIASES（土豆→马铃薯[土豆、洋芋] 等）
- 忌口/过敏：food_db.violates / filter_df；烹饪方式：food_db.cooking_method
- _pick 优先选非加工品（排除 粉/淀粉/干/酱 等）
- classify：规则优先，LLM 兜底（别改回 LLM 优先，会误判「健身计划」）
- diet_log 用 user_id="default"；记忆/偏好也用 "default"（单用户 demo）
