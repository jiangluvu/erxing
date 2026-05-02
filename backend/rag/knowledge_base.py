"""知识库管理：Milvus Lite 向量存储 + 文章元数据。"""

import json
import uuid
from pathlib import Path

import numpy as np
from pymilvus import MilvusClient, DataType, CollectionSchema, FieldSchema

from .embedder import Embedder


DIMENSION = 5000  # TF-IDF max_features


def _gen_id() -> str:
    return uuid.uuid4().hex[:12]


def _create_schema(dim: int):
    """定义 Milvus Collection 结构。"""
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=16),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
        FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="summary", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=1024),
        FieldSchema(name="content_hash", dtype=DataType.VARCHAR, max_length=32),
    ]
    return CollectionSchema(fields, description="耳行文章知识库")


class KnowledgeBase:
    """文章知识库。Milvus Lite 存向量 + articles.json 存原文。"""

    COLLECTION_NAME = "erxing_articles"
    MILVUS_DB = "milvus_lite.db"

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._articles_path = self.data_dir / "articles.json"

        # 初始化 Milvus Lite
        self._client = MilvusClient(str(self.data_dir / self.MILVUS_DB))
        self._ensure_collection()

        # 初始化向量化引擎
        self._embedder = Embedder(data_dir)

        # 加载已有数据
        self._articles: list[dict] = self._load_articles()
        if self._articles and not self._embedder.is_trained():
            self._embedder.load()
            self._reindex()

    # ── Collection 管理 ──

    def _ensure_collection(self):
        if not self._client.has_collection(self.COLLECTION_NAME):
            schema = _create_schema(DIMENSION)
            self._client.create_collection(
                collection_name=self.COLLECTION_NAME,
                schema=schema,
                index_params={
                    "metric_type": "IP",       # inner product = cosine on normalized vectors
                    "index_type": "FLAT",
                    "params": {},
                },
            )

    def _reindex(self):
        """重新向量化所有文章并更新 Milvus。"""
        if not self._articles or not self._embedder.is_trained():
            return
        texts = [a["title"] + " " + a["content"] for a in self._articles]
        vectors = self._embedder.embed_batch(texts)
        # L2 normalize for IP = cosine similarity
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        vectors = vectors / norms
        data = [
            {"id": a["id"], "vector": vectors[i].tolist(),
             "title": a["title"], "summary": a.get("summary", ""),
             "url": a.get("url", ""), "content_hash": a.get("content_hash", "")}
            for i, a in enumerate(self._articles)
        ]
        if data:
            self._client.insert(self.COLLECTION_NAME, data)

    # ── 文章持久化 ──

    def _load_articles(self) -> list[dict]:
        if not self._articles_path.exists():
            return []
        with open(self._articles_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_articles(self):
        # 只存元数据，不存 content（Milvus 存向量，content 太大）
        meta = [
            {"id": a["id"], "title": a["title"],
             "summary": a.get("summary", ""),
             "url": a.get("url", ""),
             "content_hash": a.get("content_hash", "")}
            for a in self._articles
        ]
        with open(self._articles_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    # ── 公开接口 ──

    def add(self, title: str, content: str, url: str = "", summary: str = "") -> dict:
        """添加一篇文章到知识库。返回文章对象。"""
        # 检查是否已存在（按 title + content_hash 去重）
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

        # 向量化并存入 Milvus
        if not self._embedder.is_trained():
            self._embedder.train([title + " " + content])
        vec = self._embedder.embed(title + " " + content)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        self._client.insert(self.COLLECTION_NAME, [{
            "id": article["id"],
            "vector": vec.tolist(),
            "title": title,
            "summary": article["summary"],
            "url": url,
            "content_hash": content_hash,
        }])
        self._save_articles()
        return article

    def add_many(self, articles: list[dict]):
        """批量添加文章。articles: [{title, content, url?, summary?}]"""
        if not articles:
            return
        # 首次训练：用所有文章训练 TF-IDF
        texts = []
        for a in articles:
            texts.append(a["title"] + " " + a["content"])
        self._embedder.train(texts)

        # 向量化全部
        vectors = self._embedder.embed_batch(texts)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        vectors = vectors / norms

        new_articles = []
        milvus_data = []
        for i, a in enumerate(articles):
            content_hash = uuid.uuid5(uuid.NAMESPACE_DNS, a["content"]).hex[:8]
            aid = _gen_id()
            new_articles.append({
                "id": aid, "title": a["title"],
                "content": a["content"],
                "summary": a.get("summary", a["content"][:80] + "..."),
                "url": a.get("url", ""),
                "content_hash": content_hash,
            })
            milvus_data.append({
                "id": aid, "vector": vectors[i].tolist(),
                "title": a["title"],
                "summary": new_articles[-1]["summary"],
                "url": a.get("url", ""),
                "content_hash": content_hash,
            })

        self._articles.extend(new_articles)
        self._client.insert(self.COLLECTION_NAME, milvus_data)
        self._save_articles()

    def search(self, title: str, content: str, top_k: int = 3) -> list[dict]:
        """搜索相似文章。返回 [{id, title, summary, url, distance}]"""
        if not self._articles or not self._embedder.is_trained():
            return []

        vec = self._embedder.embed(title + " " + content)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        results = self._client.search(
            collection_name=self.COLLECTION_NAME,
            data=[vec.tolist()],
            limit=top_k + 1,  # 多取 1 个用于排除自身
            output_fields=["title", "summary", "url"],
            metric_type="IP",
        )
        hits = []
        for hit in results[0]:
            if hit["distance"] < 0.1:
                continue
            hits.append({
                "id": hit["id"],
                "title": hit["entity"]["title"],
                "summary": hit["entity"]["summary"],
                "url": hit["entity"].get("url", ""),
                "similarity": round(float(hit["distance"]), 4),
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
