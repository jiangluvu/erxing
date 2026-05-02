"""向量化引擎：jieba 分词 + TF-IDF 向量化。可替换为其他嵌入模型。"""

import json
import pickle
from pathlib import Path

import jieba
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


class Embedder:
    """TF-IDF + jieba 中文文本向量化引擎。"""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._vectorizer_path = self.data_dir / "vectorizer.pkl"
        self._vectorizer: TfidfVectorizer | None = None

    # ── 分词预处理 ──

    def _tokenize(self, text: str) -> str:
        """中文分词，空格分隔。"""
        return " ".join(jieba.cut(text))

    # ── 训练 ──

    def train(self, texts: list[str]):
        """训练 TF-IDF 模型并持久化。"""
        tokenized = [self._tokenize(t) for t in texts]
        self._vectorizer = TfidfVectorizer(max_features=5000)
        self._vectorizer.fit(tokenized)
        self._save()

    def _save(self):
        if self._vectorizer:
            with open(self._vectorizer_path, "wb") as f:
                pickle.dump(self._vectorizer, f)

    def load(self) -> bool:
        """加载已训练的向量化器。返回是否加载成功。"""
        if not self._vectorizer_path.exists():
            return False
        with open(self._vectorizer_path, "rb") as f:
            self._vectorizer = pickle.load(f)
        return True

    def is_trained(self) -> bool:
        return self._vectorizer is not None

    # ── 向量化 ──

    def embed(self, text: str) -> np.ndarray:
        """将文本转为向量。返回 numpy 数组 (dim,)"""
        assert self._vectorizer is not None, "Embedder not trained"
        tokenized = self._tokenize(text)
        vec = self._vectorizer.transform([tokenized])
        return vec.toarray().flatten()

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """批量向量化。返回 (n, dim) 数组。"""
        assert self._vectorizer is not None, "Embedder not trained"
        tokenized = [self._tokenize(t) for t in texts]
        return self._vectorizer.transform(tokenized).toarray()
