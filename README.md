# 耳行 (Erxing)

> 让每一篇文章，变成一场对谈。

耳行是一款将文章、链接或文本转换为 **AI 双人对话播客** 的 Web 应用。输入一篇文章链接，AI 会自动提取核心观点，生成一段由"小羊"和"小姜"两位主持人进行的自然对话，并合成语音，让你在通勤、开车、运动时也能"听"文章。

---

## 功能特性

| 功能 | 描述 |
|------|------|
| **一键生成** | 粘贴文章链接或输入文本，一键生成双人对话播客 |
| **TTFA 极速响应** | 开场音频在 ~10 秒内就绪，无需等待完整生成即可收听 |
| **后台完整生成** | 开场播放的同时，后台自动完成全文对话生成和语音合成 |
| **自然对话风格** | 小羊（沉稳温和）与小姜（直爽接地气）的差异化角色设定 |
| **车载场景适配** | 短句、自然口语化、节奏舒适，专为通勤收听优化 |
| **探索频道** | curated 精选内容，覆盖科技、汽车、AI、文化等话题 |
| **内容源订阅** | 订阅公众号、B站、知乎等内容源，自动追踪更新 |
| **笔记与收藏** | 播客笔记随时记录，收藏喜欢的内容 |
| **历史记录** | 自动保存收听历史，支持时长偏好设置 |
| **移动端适配** | 响应式设计，支持桌面端 + 移动端底部 Tab 导航 |

---

## 技术架构

```
┌─────────────────────────────────────────┐
│           前端 (Frontend)                │
│  ┌─────────────────────────────────┐   │
│  │  单页 HTML + 原生 CSS + 原生 JS  │   │
│  │  文件: frontend/index.html        │   │
│  │  设计: 深色主题 / 品牌粉 #ec4899  │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
                    │
                    ▼ HTTP API
┌─────────────────────────────────────────┐
│           后端 (Backend)                 │
│  ┌─────────────────────────────────┐   │
│  │  Python Flask                   │   │
│  │  文件: backend/app.py           │   │
│  │                                 │   │
│  │  AI 对话生成  →  DeepSeek-v4    │   │
│  │  语音合成     →  edge-tts       │   │
│  │  音频拼接     →  ffmpeg         │   │
│  │  推荐系统     →  RAG (TF-IDF)   │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### 核心链路

```
用户输入 URL/文本
    │
    ▼
[Flask] /api/generate_streaming
    │
    ├── 快速提取标题 (~0.3s)
    ├── AI 生成开场对话 (~5s)
    ├── TTS 合成开场音频 (~2s)
    │       └── 立即返回音频流 (TTFA ~10s)
    │
    └── 后台线程：完整生成
            ├── 抓取文章正文
            ├── AI 提取核心观点
            ├── AI 生成完整对话
            ├── 自评质量打分
            └── TTS 合成完整音频
```

---

## 项目结构

```
erxing/
├── frontend/
│   ├── index.html              # 单页应用（CSS + HTML + JS 合一）
│   └── design-ref/             # 上游设计参考（只读）
│       ├── web.html            # 桌面端界面原型
│       ├── design-tokens.json  # 颜色/间距/字体令牌
│       └── components.md       # 组件清单和交互说明
│
├── backend/
│   ├── app.py                  # Flask 主应用
│   ├── rag/                    # RAG 推荐模块
│   │   ├── __init__.py
│   │   ├── embedder.py         # TF-IDF + jieba 向量化
│   │   ├── knowledge_base.py   # 向量知识库
│   │   ├── recommender.py      # 推荐引擎
│   │   └── seed_articles.py    # 种子文章数据
│   ├── .env                    # 环境变量（API Key）
│   ├── notes.jsonl             # 笔记数据（自动创建）
│   ├── subscriptions.jsonl     # 订阅数据（自动创建）
│   └── logs.jsonl              # 运行日志（自动创建）
│
├── start_flask.py              # Flask 启动脚本
└── README.md                   # 本文件
```

---

## 快速开始

### 环境要求

- Python 3.10+
- ffmpeg（语音拼接依赖）

### 安装依赖

```bash
pip install flask flask-cors requests beautifulsoup4 readability-lxml python-dotenv anthropic edge-tts jieba scikit-learn numpy
```

### 配置环境变量

复制 `backend/.env.example` 为 `backend/.env`，填入 API Key：

```bash
ZHI_API_KEY=your_api_key_here
```

API 使用 [zhizengzeng](https://api.zhizengzeng.com) 提供的 DeepSeek-v4-flash 和 GPT-4o-mini 兼容端点。

### 启动服务

```bash
python start_flask.py
```

服务默认运行在 `http://localhost:5002`。

打开浏览器访问即可使用。

---

## RAG 推荐系统

耳行的推荐系统基于 **RAG (Retrieval-Augmented Generation)** 架构，使用 TF-IDF + Milvus Lite 实现向量检索，在播客播放完毕后为用户推荐相似文章。

### 架构概览

```
用户生成播客
    │
    ▼
[app.py] /api/recommend
    │
    ├── 获取文章 title + content
    ├── 调用 KnowledgeBase.search()
    │       │
    │       ├── jieba 分词 + TF-IDF 向量化
    │       ├── L2 归一化
    │       └── Milvus Lite IP 检索
    │
    └── 返回 top-3 相似文章
```

### 模块详解

#### 1. Embedder — 向量化引擎 (`rag/embedder.py`)

使用 **TF-IDF + jieba 中文分词** 实现轻量级文本向量化，无需 GPU，本地即可运行。

| 参数 | 值 | 说明 |
|------|-----|------|
| 分词器 | jieba | 中文分词，空格分隔 |
| 向量维度 | 5000 | `max_features=5000` |
| 持久化 | pickle | 训练后保存为 `vectorizer.pkl` |
| 训练触发 | 首次批量添加 | `add_many()` 时自动训练 |

```python
# 分词示例
"小米SU7上市三个月" → "小米 SU7 上市 三个 月"

# 向量化流程
text → jieba 分词 → TF-IDF 变换 → 5000 维稀疏向量 → toarray().flatten()
```

#### 2. KnowledgeBase — 向量知识库 (`rag/knowledge_base.py`)

基于 **Milvus Lite**（嵌入式向量数据库，无需独立服务）存储文章向量及元数据。

**Collection 结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR | 主键，12 位 hex |
| `vector` | FLOAT_VECTOR | 5000 维，L2 归一化 |
| `title` | VARCHAR | 文章标题 |
| `summary` | VARCHAR | 内容摘要 |
| `url` | VARCHAR | 来源链接 |
| `content_hash` | VARCHAR | 内容去重指纹 |

**相似度计算：**

- 度量方式：`IP` (Inner Product)
- 由于向量经过 L2 归一化，`IP` 等价于 **余弦相似度**
- 返回的 `distance` 范围：`[0, 1]`，越接近 1 越相似
- 过滤阈值：`distance < 0.1` 的结果被丢弃

**去重机制：**

- `content_hash = uuid.uuid5(NAMESPACE_DNS, content).hex[:8]`
- 同一 `title + content_hash` 的文章不会重复入库

**数据持久化：**

| 文件 | 内容 | 位置 |
|------|------|------|
| `milvus_lite.db` | 向量数据 | `backend/rag/data/` |
| `articles.json` | 文章元数据 | `backend/rag/data/` |
| `vectorizer.pkl` | TF-IDF 模型 | `backend/rag/data/` |

#### 3. 种子数据 (`rag/seed_articles.py`)

系统预置 **15 篇** 跨领域种子文章，确保首次部署即有推荐结果：

| # | 领域 | 标题 |
|---|------|------|
| 1 | AI | DeepSeek 崛起：中国 AI 大模型的新格局 |
| 2 | 汽车 | 小米 SU7 上市三个月，真实用户体验报告 |
| 3 | 健康 | 2025 年最佳作息时间表：科学睡眠指南 |
| 4 | 投资 | 2025 年 A 股投资策略：结构性机会在哪里 |
| 5 | 汽车 | 特斯拉 FSD 入华：自动驾驶的新篇章 |
| 6 | 健康 | 减脂期饮食指南：科学搭配不挨饿 |
| 7 | 电商 | 小红书电商的崛起：从种草到拔草 |
| 8 | 汽车 | 问界 M9 深度体验：华为技术的集大成者 |
| 9 | 理财 | 普通人如何建立被动收入体系 |
| 10 | 航天 | SpaceX 星舰第五飞：人类登陆火星的里程碑 |
| 11 | 科技 | 2025 年最值得关注的 10 个科技趋势 |
| 12 | 汽车 | 比亚迪秦 L DM-i 实测：油耗 2 升时代来了 |
| 13 | 健康 | 为什么你总是睡不好？失眠的真相与解法 |
| 14 | 游戏 | 《黑神话：悟空》DLC 前瞻：新篇章的期待 |
| 15 | AI | 国产大模型全面对比：谁是你的最佳选择 |

#### 4. 初始化流程 (`rag/__init__.py`)

采用**全局单例 + 懒加载**模式：

1. 首次调用 `init_knowledge_base()` 时创建 `KnowledgeBase` 实例
2. 检查 `articles.json` 是否为空
3. 若为空，自动加载 15 篇 `SEED_ARTICLES`
4. 后续调用直接返回已有实例

```python
from rag import init_knowledge_base
kb = init_knowledge_base()  # 首次调用会自动加载种子数据
```

#### 5. 推荐 API (`app.py`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `POST /api/recommend` | 请求：`{title, content}` | 返回 top-3 相似文章（含相似度百分比） |
| `POST /api/recommend/add` | 请求：`{title, content, url?, summary?}` | 将文章加入知识库，用于后续推荐 |

**使用场景：**

- 播客播放结束后，前端自动调用 `/api/recommend`，传入当前文章标题和正文
- 后端搜索知识库，返回相似度最高的 3 篇文章
- 用户点击推荐卡片，即可跳转回首页生成新的播客

### 性能特点

- **无外部依赖**：Milvus Lite 为嵌入式数据库，无需独立部署向量服务
- **CPU 即可运行**：TF-IDF + jieba 无需 GPU，本地推理延迟 < 100ms
- **自动持久化**：向量、模型、元数据均落盘，重启后自动加载
- **可替换嵌入模型**：`Embedder` 接口统一，未来可无缝替换为 sentence-transformers 或 OpenAI Embedding

---

## API 文档

### 播客生成

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/generate_streaming` | POST | TTFA 流式生成，返回开场音频 mp3 |
| `/api/generation_status/<sid>` | GET | 查询生成进度和状态 |
| `/api/download_podcast/<sid>` | GET | 下载完整播客音频 mp3 |

### 内容探索

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/explore?platform=` | GET | 获取精选内容列表 |
| `/api/podcast/<sid>/detail` | GET | 获取播客详情（含章节大纲） |

### 笔记

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/notes` | GET | 获取所有笔记 |
| `/api/notes` | POST | 创建笔记 `{session_id, title, content}` |
| `/api/notes?id=` | DELETE | 删除笔记 |

### 订阅

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/subscriptions` | GET | 获取所有订阅 |
| `/api/subscriptions` | POST | 创建订阅 `{url, name, platform}` |
| `/api/subscriptions?id=` | DELETE | 删除订阅 |

### 推荐

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/recommend` | POST | 基于标题+内容推荐相似文章 |

---

## 设计系统

### 颜色令牌

| 令牌 | 值 | 用途 |
|------|-----|------|
| `bg-main` | `#0c0c0e` | 页面主背景 |
| `bg-sidebar` | `#1a1a1a` | 侧边栏背景 |
| `bg-card` | `#161618` | 卡片/面板背景 |
| `border` | `#2a2a2a` | 边框/分割线 |
| `text-primary` | `#ffffff` | 主标题文字 |
| `text-secondary` | `#a0a0a0` | 次要文字 |
| `text-muted` | `#52525b` | 占位符/禁用态 |
| `brand-pink` | `#ec4899` | 品牌色/主按钮 |
| `brand-tertiary` | `#52dea2` | 辅助色/成功态 |

### 响应式断点

- 桌面端：`> 768px`，显示左侧 240px 侧边栏
- 移动端：`≤ 768px`，隐藏侧边栏，显示底部 Tab 导航 + 汉堡菜单抽屉

---

## 角色设定

| 角色 | 声音 | 性格 | 风格 |
|------|------|------|------|
| **小羊** | zh-CN-YunxiNeural | 沉稳温和，善于引导话题、总结观点 | 句子完整，带知识性，有条理 |
| **小姜** | zh-CN-XiaoxiaoNeural | 直爽接地气，从实用角度思考 | 短句为主，用生活经历佐证，喜欢反问 |

---

## 存储说明

| 数据类型 | 存储方式 | 文件位置 |
|----------|----------|----------|
| 笔记 | JSONL | `backend/notes.jsonl` |
| 订阅 | JSONL | `backend/subscriptions.jsonl` |
| 运行日志 | JSONL | `backend/logs.jsonl` |
| 历史记录 | localStorage | 浏览器本地 |
| 收藏 | localStorage | 浏览器本地 |
| 生成次数 | localStorage | 浏览器本地 |
| 时长偏好 | localStorage | 浏览器本地 |

---

## 开发规则

> 详见 `.claude/CLAUDE.md`

- 前端为单文件 `frontend/index.html`，原生 CSS + JS，不引入构建工具
- 设计参考文件位于 `frontend/design-ref/`，只读不可修改
- 颜色、间距必须使用设计令牌中的值
- 后端新增 API 统一写在 `backend/app.py`
- 发现设计矛盾时回上游讨论，不在下游私自改动

---

## License

MIT
