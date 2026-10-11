"""一键准备：构建知识库索引（食物数据已在 data/food_db.csv）。

用法：python scripts/bootstrap.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402
from src.rag.corpus import load_corpus  # noqa: E402
from src.rag.retriever import build, save  # noqa: E402


def main() -> None:
    if not config.FOOD_DB_FILE.exists():
        print("提示：data/food_db.csv 不存在，先运行 python scripts/00_fetch_food_data.py")
        return
    chunks = load_corpus()
    save(build(chunks))
    print(f"知识库索引已构建：{len(chunks)} 块 -> {config.KB_INDEX}")
    print("启动服务：python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000")


if __name__ == "__main__":
    main()
