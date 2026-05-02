"""RAG 模块初始化。创建全局知识库实例并加载种子数据。"""

import logging
from pathlib import Path

from .knowledge_base import KnowledgeBase
from .seed_articles import SEED_ARTICLES

logger = logging.getLogger("erxing.rag")

DATA_DIR = Path(__file__).parent / "data"

# 全局单例
kb: KnowledgeBase | None = None


def init_knowledge_base():
    """初始化知识库，加载种子数据（如尚未加载）。"""
    global kb
    if kb is not None:
        return kb

    kb = KnowledgeBase(DATA_DIR)

    # 如果知识库为空，加载种子数据
    if kb.count() == 0:
        logger.info(f"Loading {len(SEED_ARTICLES)} seed articles...")
        kb.add_many(SEED_ARTICLES)
        logger.info(f"Knowledge base initialized with {kb.count()} articles")
    else:
        logger.info(f"Knowledge base already has {kb.count()} articles, skipping seed")

    return kb
