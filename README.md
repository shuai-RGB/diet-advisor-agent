# 健康助手 · 多 Agent 智能体

一个**真实数据驱动、可评测、可观测、可降级**的多 Agent 健康助手。以对话为核心入口，
由 8 个 Agent 协作，覆盖 **营养目标、一日三餐+烹饪方式、饮食记录分析、附近采购、天气、锻炼建议、知识问答**，
并带 **长期记忆 + 偏好学习**。

> 核心主张：大模型只做「大脑」（ReAct 推理、意图路由、文案、报告摘要）；
> 营养计算、食谱约束优化、忌口校验等确定性逻辑走专门算法，不交给 LLM。
> LLM 不可用时自动降级到规则引擎，系统离线也能跑。

---

## 一、核心能力

| 能力 | 入口 | 说明 |
|------|------|------|
| 多轮对话 | 聊天页 | ReAct 引擎，缺信息自动追问，多轮记忆 |
| 营养目标 | 首页 / 聊天 | Mifflin-St Jeor 公式 + BMI + 每日热量/蛋白/脂肪/碳水 |
| 三餐 + 做法 | 聊天 | 从 4857 种食物搭配三餐，每道菜附烹饪方式 |
| 附近采购 | 聊天 | 高德搜超市/菜市场，支持定位算距离排序 |
| 天气 + 锻炼 | 聊天 | 高德天气 + 按目标给运动建议（雨天→室内） |
| 饮食记录 | 聊天 | 「我吃了米饭200克」→ 解析 → 存 SQLite → 今日摄入进度 |
| 知识问答 | 聊天 | RAG 检索膳食指南 |
| 一天报告 | 聊天 | 多轮追问收集信息后，输出「饮食+锻炼」完整报告 |

## 二、架构

```
用户输入（表单 / 对话）
        │
        ▼
  ┌────────────┐  ReAct 引擎：LLM 自主 tool-calling
  │ 对话路由    │  7 个工具：算目标/生成三餐/查天气/找超市/查知识/查食物/追问
  └─────┬──────┘
        ▼
  ┌────────────┐
  │ 8 Agent DAG │  路由 → 画像 → [食谱规划 ∥ 知识召回 ∥ 附近采购] → 校验 → 报告
  │ (LangGraph) │  + 反馈循环（校验不达标 → 发消息重规划）
  └─────┬──────┘
        ▼
  可靠性层（重试 / 熔断 / 降级 / 成本预算）
```

**三层设计**：ReAct（LLM 推理）→ 确定性 Agent（数值逻辑）→ 可靠性层（兜底）。

## 三、真实数据

- **食物营养**：《中国食物成分表标准版(第6版)》**4857 种真实食物**（每 100g 能量/蛋白/脂肪/碳水/纤维/钠）。
- **膳食指南**：《中国居民膳食指南(2022)》八条准则（RAG 知识库，`data/knowledge/*.md`）。
- **地图/天气**：高德 Web 服务 API（POI 周边搜索 + 天气 + 逆地理编码）。
- **LLM**：OpenAI 兼容接口（DeepSeek），未配置/故障时回退离线规则引擎。

## 四、工程亮点（六个升级项）

| 项 | 说明 | 验证方式 |
|----|------|---------|
| ① 评测体系 | 黄金数据集 + 指标 + 回归 | `python scripts/eval.py` |
| ② ReAct + tool-calling | LLM 自主决定调工具/追问，非 if-else | 聊天「我想锻炼」→追问城市→查天气 |
| ③ 可观测性 | 逐节点耗时 / token / 成本 / 甘特图 | 导航「监控」页 |
| ④ 记忆个性化 | 长期记忆 + 从饮食记录学偏好 | 说「我不吃辣」→下次记得 |
| ⑤ 可靠性 | 重试/熔断/降级/成本预算 | 断网自动切规则引擎 |
| ⑥ 并行 + 反馈循环 | 三 Agent 并行 + 校验重规划 | 右下角「Agent 流程」 |

**验收结果**：`python scripts/acceptance.py` → **14/14 通过**。
**评测指标**：意图识别 45/45、食物检索 35/35、热量偏差 0.0%。

## 五、快速开始

```bash
cd diet-advisor-agent
pip install -r requirements.txt
python scripts/00_fetch_food_data.py   # 食物成分表 -> data/food_db.csv
python scripts/bootstrap.py            # RAG 索引
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

浏览器 <http://127.0.0.1:8000>（首页 / 聊天 / 监控 / Agent 流程小窗）。

配置 `.env`：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`AMAP_KEY`。

## 六、API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 多轮对话（ReAct，带记忆/偏好/定位） |
| POST | `/api/plan/steps` | 完整方案 + 逐节点过程（供流程图） |
| POST | `/api/goal` `/api/meal-plan` `/api/analyze` | 目标 / 三餐 / 分析 |
| POST | `/api/where-to-eat` | 附近采购 |
| POST | `/api/query` | 知识问答 |
| POST | `/api/dashboard` | 仪表盘（目标+今日摄入+最近方案/采购） |
| GET | `/api/observability` | 监控（耗时/token/成本/熔断/预算） |
| GET | `/api/weather` `/api/regeo` | 天气 / 逆地理编码 |
| GET | `/api/trace/{id}` `/api/health` | 溯源 / 健康检查 |

## 七、项目结构

```
diet-advisor-agent/
├── src/
│   ├── config.py / llm.py            # 配置 / LLM（可插拔+可靠性）
│   ├── reliability.py                # 重试/熔断/成本预算
│   ├── react_agent.py                # ReAct + tool-calling 引擎
│   ├── chat.py                       # 聊天入口（多轮记忆/画像记忆/追问）
│   ├── data/                         # food_db / profile / meal_planner / diet_analyzer / storage(SQLite)
│   ├── tools/amap.py                 # 高德（POI/周边/天气/逆地理）
│   ├── rag/                          # 语料分块 / BM25+TF-IDF 混合检索 / 重排
│   ├── agents/                       # 8 个 Agent
│   ├── graph/workflow.py             # LangGraph 编排 + plan_steps + trace
│   ├── trace/tracer.py               # 溯源落库
│   └── api/                          # FastAPI + 请求模型
├── web/index.html                    # 前端（首页/聊天/监控/过程展示器）
├── data/food_db.csv                  # 4857 种真实食物
├── data/knowledge/*.md               # 膳食指南知识库
├── data/eval/*.json                  # 评测黄金数据集
├── scripts/                          # fetch / bootstrap / smoke / benchmark / eval / acceptance
└── Dockerfile / docker-compose.yml
```

## 八、工程决策（面试可展开）

1. **LLM 与确定性逻辑解耦**：营养计算/优化/校验走算法，LLM 只做语义与文案；无 key 或故障自动降级。
2. **ReAct 而非 if-else**：路由层是 LLM 驱动的 Thought→Action→Observation 循环，通过函数调用自主决定问什么、调哪个工具。
3. **并行 DAG + 反馈循环**：食谱规划/知识召回/附近采购三路并行；校验不达标发消息重规划（显式通信）。
4. **评测驱动**：黄金数据集 + 指标，每次改动跑 `eval.py` 就是回归测试。
5. **可观测性驱动优化**：监控发现 report 节点重复执行，修复后耗时降 38%、token 降 49%。
6. **真实数据闭环**：食物成分表 + 膳食指南 + 高德，全部真实可引用，无合成数据。

## 九、免责声明

营养目标与食谱基于公开公式与《食物成分表》估算，仅供参考，不构成医疗/营养处方建议；特殊健康状况请咨询专业医师或注册营养师。
