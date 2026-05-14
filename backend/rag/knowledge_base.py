"""知识库管理：内存向量存储 + 文章元数据。无需 Milvus / sklearn。"""

import json
import uuid
from pathlib import Path

import numpy as np

from .embedder import Embedder


def _gen_id() -> str:
    return uuid.uuid4().hex[:12]


class KnowledgeBase:
    """文章知识库。内存存向量 + articles.json 存元数据。"""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._articles_path = self.data_dir / "articles.json"
        self._vectors_path = self.data_dir / "vectors.npy"

        self._embedder = Embedder(data_dir)

        # 加载已有数据
        self._articles: list[dict] = self._load_articles()
        self._vectors: np.ndarray | None = self._load_vectors()

    # ── 持久化 ──

    def _load_articles(self) -> list[dict]:
        if not self._articles_path.exists():
            return []
        with open(self._articles_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_articles(self):
        # 只存元数据（content 太大，单独存在内存对象里）
        meta = [
            {"id": a["id"], "title": a["title"],
             "summary": a.get("summary", ""),
             "url": a.get("url", ""),
             "content_hash": a.get("content_hash", "")}
            for a in self._articles
        ]
        with open(self._articles_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _load_vectors(self) -> np.ndarray | None:
        if not self._vectors_path.exists():
            return None
        return np.load(self._vectors_path, allow_pickle=False)

    def _save_vectors(self):
        if self._vectors is not None:
            np.save(self._vectors_path, self._vectors)

    def _reindex(self):
        """重新向量化所有文章。"""
        if not self._articles:
            self._vectors = None
            return
        texts = [a["title"] + " " + a["content"] for a in self._articles]
        self._vectors = self._embedder.embed_batch(texts)
        # L2 normalize for cosine similarity
        norms = np.linalg.norm(self._vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        self._vectors = self._vectors / norms
        self._save_vectors()

    # ── 公开接口 ──

    def add(self, title: str, content: str, url: str = "", summary: str = "") -> dict:
        """添加一篇文章到知识库。返回文章对象。"""
        content_hash = uuid.uuid5(uuid.NAMESPACE_DNS, content).hex[:8]
        for a in self._articles:
            if a.get("title") == title and a.get("content_hash") == content_hash:
                return a  # 已存在

        article = {
            "id": _gen_id(),
            "title": title,
            "content": content,
            "summary": summary or content[:80] + "...",
            "url": url,
            "content_hash": content_hash,
        }
        self._articles.append(article)

        # 向量化
        if not self._embedder.is_trained():
            self._embedder.train([title + " " + content])
            self._reindex()
        else:
            vec = self._embedder.embed(title + " " + content)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            if self._vectors is None:
                self._vectors = vec.reshape(1, -1)
            else:
                self._vectors = np.vstack([self._vectors, vec])
            self._save_vectors()

        self._save_articles()
        return article

    def add_many(self, articles: list[dict]):
        """批量添加文章。"""
        if not articles:
            return
        texts = []
        for a in articles:
            texts.append(a["title"] + " " + a["content"])
        self._embedder.train(texts)

        new_articles = []
        for a in articles:
            content_hash = uuid.uuid5(uuid.NAMESPACE_DNS, a["content"]).hex[:8]
            new_articles.append({
                "id": _gen_id(), "title": a["title"],
                "content": a["content"],
                "summary": a.get("summary", a["content"][:80] + "..."),
                "url": a.get("url", ""),
                "content_hash": content_hash,
            })

        self._articles.extend(new_articles)
        self._reindex()
        self._save_articles()

    def search(self, title: str, content: str, top_k: int = 3) -> list[dict]:
        """搜索相似文章。返回 [{id, title, summary, url, similarity}]"""
        if not self._articles or not self._embedder.is_trained() or self._vectors is None:
            return []

        vec = self._embedder.embed(title + " " + content)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        # 余弦相似度 = 点积（因为向量已归一化）
        similarities = self._vectors @ vec
        # 获取 top_k 索引
        top_indices = np.argsort(similarities)[::-1][:top_k + 1]

        hits = []
        for idx in top_indices:
            sim = float(similarities[idx])
            if sim < 0.05:
                continue
            a = self._articles[idx]
            hits.append({
                "id": a["id"],
                "title": a["title"],
                "summary": a.get("summary", ""),
                "url": a.get("url", ""),
                "similarity": round(sim, 4),
            })
        return hits[:top_k]

    def count(self) -> int:
        return len(self._articles)

    def list_articles(self) -> list[dict]:
        """返回文章列表（不含 content，仅元数据）。"""
        return [
            {"id": a["id"], "title": a["title"],
             "summary": a.get("summary", ""),
             "url": a.get("url", "")}
            for a in self._articles
        ]
