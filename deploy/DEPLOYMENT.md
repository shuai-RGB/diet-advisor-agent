# 部署说明

## 一、本地运行（局域网可访问）

```bash
cd diet-advisor-agent
pip install -r requirements.txt
python scripts/bootstrap.py             # 构建 RAG 索引（知识库 10 个文件 → 205 块）
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

- 本机：<http://127.0.0.1:8000>
- 局域网：`http://<你的IP>:8000`（Windows 查 IP：`ipconfig`）

## 二、Docker 部署

```bash
cd diet-advisor-agent
docker compose up --build -d
# 访问 http://localhost:8000
```

> 镜像构建期执行 `bootstrap.py` 构建 RAG 索引；`data/food_db.csv` 已随源码打进镜像。

## 三、云平台上线（推荐，无需 Docker）

### Railway / Render（最省事）

1. 把项目推到 **GitHub**（注意 `.env` 不要提交，`.gitignore` 已忽略）
2. Railway：<https://railway.app> → New Project → Deploy from GitHub → 选仓库
3. Render：<https://render.com> → New Web Service → 连 GitHub → 选仓库

**Render 关键配置**：

| 项 | 值 |
|----|----|
| Build Command | `pip install -r requirements.txt && python scripts/bootstrap.py` |
| Start Command | `uvicorn src.api.main:app --host 0.0.0.0 --port $PORT` |

**环境变量**（两个平台都一样）：

| 变量 | 说明 | 必需 |
|------|------|------|
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | OpenAI 兼容 LLM | 否（留空用规则引擎，能跑但笨） |
| `AMAP_KEY` | 高德 Web 服务 key | 否（附近采购/天气/定位才需要） |

高德 key 申请：<https://console.amap.com>（「Web 服务」类型，免费有每日配额）。

### 其它选项

- **Fly.io**：`fly launch`（会自动用 Dockerfile）
- **HuggingFace Spaces**：选 Docker SDK，填 Dockerfile

## 四、环境变量（.env）

```
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
AMAP_KEY=xxx
```

## 五、API 示例

```bash
# 多轮对话（ReAct，带记忆/偏好）
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" \
  -d '{"message":"帮我生成减脂方案，175cm 70kg"}'

# 营养目标
curl -X POST http://localhost:8000/api/goal -H "Content-Type: application/json" \
  -d '{"sex":"男","age":25,"height_cm":175,"weight_kg":70,"activity":"中度","goal":"减脂"}'

# 附近采购
curl -X POST http://localhost:8000/api/where-to-eat -H "Content-Type: application/json" \
  -d '{"city":"北京"}'

# 监控
curl http://localhost:8000/api/observability
```

## 六、验收 & 评测

```bash
python scripts/acceptance.py   # 14 项验收
python scripts/eval.py         # 意图/食物检索/热量偏差
python scripts/benchmark.py    # 食谱规划基准
```

## 七、生产化建议

- SQLite 是单机存储；多实例部署时换 PostgreSQL（`src/data/storage.py` 只改连接即可）
- `data/artifacts/trace.jsonl` 和 SQLite 的 traces 表接入集中式日志/监控
- 高德 API 有每日配额与并发限制：接 Redis 缓存 POI、做限流
- 加用户鉴权、请求限流、敏感信息脱敏
- 食物成分表定期更新 + 后台重建索引
