"""混合检索：BM25 + TF-IDF（中文单字 + bigram），可持久化、全离线。"""
from __future__ import annotations

import re

import joblib
import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer

from .. import config


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens: list[str] = []
    for m in re.finditer(r"[a-z0-9]+", text):
        tokens.append(m.group())
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.extend(list(run))
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def _norm(a: np.ndarray) -> np.ndarray:
    mx = float(a.max()) if a.size else 0.0
    if mx == 0.0:
        return np.zeros_like(a, dtype=float)
    return a / mx


class HybridRetriever:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        texts = [c["text"] for c in chunks]
        self.tokenized = [_tokenize(t) for t in texts]
        self.bm25 = BM25Okapi(self.tokenized)
        self.vectorizer = TfidfVectorizer(tokenizer=_tokenize, token_pattern=None, lowercase=False)
        self.tfidf = self.vectorizer.fit_transform(texts)

    def search(self, query: str, k: int = 5, alpha: float = 0.5) -> list[dict]:
        q_tok = _tokenize(query)
        bm25_scores = np.array(self.bm25.get_scores(q_tok))
        q_vec = self.vectorizer.transform([query])
        tfidf_scores = np.asarray(self.tfidf.dot(q_vec.T).toarray()).ravel()
        hybrid = alpha * _norm(bm25_scores) + (1 - alpha) * _norm(tfidf_scores)
        order = np.argsort(hybrid)[::-1][:k]
        out = []
        for idx in order:
            c = dict(self.chunks[idx])
            c.update({
                "bm25": round(float(bm25_scores[idx]), 4),
                "tfidf": round(float(tfidf_scores[idx]), 4),
                "score": round(float(hybrid[idx]), 4),
            })
            out.append(c)
        return out


def build(chunks: list[dict]) -> HybridRetriever:
    return HybridRetriever(chunks)


def save(retriever: HybridRetriever, path=None) -> None:
    joblib.dump(retriever, path or str(config.KB_INDEX))


def load(path=None) -> HybridRetriever:
    return joblib.load(path or str(config.KB_INDEX))
