"""向量化引擎：jieba 分词 + 纯 numpy TF-IDF。无需 sklearn。"""

import json
import math
from pathlib import Path

import jieba
import numpy as np


class Embedder:
    """TF-IDF + jieba 中文文本向量化引擎（纯 numpy 实现）。"""

    def __init__(self, data_dir: str | Path, max_features: int = 5000):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._vocab_path = self.data_dir / "vocab.json"
        self._idf_path = self.data_dir / "idf.json"
        self.max_features = max_features

        self._vocab: dict[str, int] = {}  # word -> index
        self._idf: np.ndarray | None = None
        self._trained = False

    # ── 分词预处理 ──

    def _tokenize(self, text: str) -> list[str]:
        """中文分词，返回词列表。"""
        return list(jieba.cut(text.strip()))

    # ── 训练 ──

    def train(self, texts: list[str]):
        """训练 TF-IDF 模型并持久化。"""
        # 分词
        tokenized = [self._tokenize(t) for t in texts]

        # 统计全局词频，选出 top max_features 个词
        word_freq = {}
        for tokens in tokenized:
            for w in tokens:
                if len(w) < 2:
                    continue
                word_freq[w] = word_freq.get(w, 0) + 1

        top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[: self.max_features]
        self._vocab = {w: i for i, (w, _) in enumerate(top_words)}

        # 计算 IDF
        n_docs = len(tokenized)
        idf = np.zeros(len(self._vocab), dtype=np.float32)
        for tokens in tokenized:
            seen = set(tokens)
            for w in seen:
                if w in self._vocab:
                    idf[self._vocab[w]] += 1

        idf = np.log((1 + n_docs) / (1 + idf)) + 1
        self._idf = idf
        self._trained = True
        self._save()

    def _save(self):
        with open(self._vocab_path, "w", encoding="utf-8") as f:
            json.dump(self._vocab, f, ensure_ascii=False, indent=2)
        if self._idf is not None:
            np.save(self._idf_path, self._idf)

    def load(self) -> bool:
        if not self._vocab_path.exists() or not self._idf_path.exists():
            return False
        with open(self._vocab_path, "r", encoding="utf-8") as f:
            self._vocab = json.load(f)
        self._idf = np.load(self._idf_path, allow_pickle=False)
        self._trained = True
        return True

    def is_trained(self) -> bool:
        return self._trained

    # ── 向量化 ──

    def embed(self, text: str) -> np.ndarray:
        """将文本转为向量。返回 numpy 数组 (dim,)"""
        assert self._trained, "Embedder not trained"
        tokens = self._tokenize(text)
        vec = np.zeros(len(self._vocab), dtype=np.float32)
        for w in tokens:
            if w in self._vocab:
                vec[self._vocab[w]] += 1
        if vec.sum() > 0:
            tf = vec / vec.sum()
            vec = tf * self._idf
        return vec

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """批量向量化。返回 (n, dim) 数组。"""
        assert self._trained, "Embedder not trained"
        return np.stack([self.embed(t) for t in texts], axis=0)
