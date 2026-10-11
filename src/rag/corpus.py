"""知识库语料加载与分块：按空行分段落，并把「标题·小节」拼进每块，保留上下文。"""
from __future__ import annotations

from pathlib import Path

from .. import config


def load_corpus(knowledge_dir: Path | None = None) -> list[dict]:
    kdir = Path(knowledge_dir) if knowledge_dir else config.KNOWLEDGE_DIR
    chunks: list[dict] = []
    for f in sorted(kdir.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        title = f.stem
        section = ""
        paragraphs: list[tuple[str, str]] = []
        current: list[str] = []
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("# "):
                title = s[2:].strip()
            elif s.startswith("## "):
                if current:
                    paragraphs.append((section, "\n".join(current)))
                    current = []
                section = s[3:].strip()
            elif s == "":
                if current:
                    paragraphs.append((section, "\n".join(current)))
                    current = []
            else:
                current.append(line)
        if current:
            paragraphs.append((section, "\n".join(current)))

        for sec, body in paragraphs:
            body = body.strip()
            if not body:
                continue
            head = f"{title} · {sec}" if sec else title
            chunks.append({
                "id": f"{f.stem}::{len(chunks)}", "doc": f.name,
                "title": title, "text": f"{head}：{body}",
            })
    return chunks
