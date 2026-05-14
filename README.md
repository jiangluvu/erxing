# 播刻 (Podcraft)

> 你的文章，值得被听见。

播刻是**知识创作者的 AI 播客化助手**。输入公众号、知乎或小红书文章链接（或粘贴文本），AI 自动提取核心观点，生成由"小羊"与"小姜"两位主持人进行的自然对话播客，并输出可直接上架小宇宙、喜马拉雅的音频文件。

从 4 小时制作到 5 分钟完成——让深度文章拥有声音。

---

## 功能特性

| 功能 | 描述 |
|------|------|
| **一键播客化** | 粘贴文章链接或输入文本，一键生成双人对话播客 |
| **TTFA 极速响应** | 开场音频在 ~10 秒内就绪，无需等待完整生成即可试听 |
| **后台完整生成** | 开场播放的同时，后台自动完成全文对话生成和语音合成 |
| **AI 双人对话** | 小羊（沉稳温和）与小姜（直爽接地气）的差异化角色演绎，非单调朗读 |
| **直接上架标准** | 自动响度标准化 + 智能音频后处理，达到小宇宙/喜马拉雅发布标准 |
| **探索灵感** | curated 热门文章推荐，一键试听/生成，解决选题焦虑 |
| **灵感订阅** | 订阅目标作者或专栏，追踪更新并一键播客化 |
| **创作者内容库** | 播客管理、收藏、历史记录、合集归类，支持系列化运营 |
| **对话文稿同步** | 播放时高亮当前说话角色，支持按文稿跳转 |
| **移动端适配** | 响应式设计，支持桌面端 + 移动端 |

---

## 为谁而生

**核心用户**：中文互联网知识类创作者
- 公众号作者、知乎答主、小红书图文博主
- Newsletter 写作者、独立博客博主

**核心场景**：
- 写了一篇深度文章，想同步做成播客分发到小宇宙
- 积累了很多文字内容，希望低成本转化为音频资产
- 想尝试播客形态，但不懂录音、剪辑和后期

---

## 技术架构

```
┌─────────────────────────────────────────┐
│           前端 (Frontend)                │
│  React 18 + Vite + Tailwind CSS + Zustand │
│  文件: frontend/src/                     │
│  设计: 深色主题 / 品牌粉 #ec4899         │
└─────────────────────────────────────────┘
                    │
                    ▼ HTTP API
┌─────────────────────────────────────────┐
│           后端 (Backend)                 │
│  Python Flask                            │
│  文件: backend/app.py                    │
│                                          │
│  AI 对话生成  →  DeepSeek-v4 / GPT-4o    │
│  语音合成     →  edge-tts                │
│  音频处理     →  ffmpeg                  │
│  推荐系统     →  RAG (TF-IDF)            │
└─────────────────────────────────────────┘
```

### 核心链路

```
创作者输入 URL/文本
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
            └── TTS 合成完整音频 + 后处理
```

---

## 项目结构

```
erxing/
├── frontend/
│   ├── src/
│   │   ├── pages/          # 页面组件
│   │   ├── components/     # 公共组件
│   │   ├── hooks/          # 业务 Hook
│   │   ├── api.js          # API 封装
│   │   └── store.js        # Zustand 状态管理
│   ├── index.html
│   └── design-ref/         # 设计参考（只读）
│       ├── components.md
│       └── design-tokens.json
│
├── backend/
│   ├── app.py              # Flask 主应用
│   ├── rag/                # RAG 推荐模块
│   │   ├── __init__.py
│   │   ├── embedder.py
│   │   ├── knowledge_base.py
│   │   ├── recommender.py
│   │   └── seed_articles.py
│   ├── .env                # 环境变量（API Key）
│   ├── notes.jsonl         # 笔记数据（自动创建）
│   ├── subscriptions.jsonl # 订阅数据（自动创建）
│   └── logs.jsonl          # 运行日志（自动创建）
│
├── PRD_播刻_Podcraft.md      # 产品需求文档
├── docs/
│   └── next_phase_product_strategy.md
└── README.md               # 本文件
```

---

## 快速开始

### 环境要求

- Python 3.10+
- ffmpeg（语音处理依赖）
- Node.js 18+（前端构建）

### 安装依赖

```bash
# 后端
pip install flask flask-cors requests beautifulsoup4 readability-lxml python-dotenv anthropic edge-tts jieba scikit-learn numpy

# 前端
cd frontend && npm install
```

### 配置环境变量

复制 `backend/.env.example` 为 `backend/.env`，填入 API Key：

```bash
ZHI_API_KEY=your_api_key_here
```

API 使用 [zhizengzeng](https://api.zhizengzeng.com) 提供的兼容端点。

### 启动服务

```bash
# 后端
python start_flask.py

# 前端（新终端）
cd frontend && npm run dev
```

后端默认运行在 `http://localhost:5000`，前端在 `http://localhost:5173`。

---

## RAG 推荐系统

播刻的推荐系统基于 **RAG (Retrieval-Augmented Generation)** 架构，使用 TF-IDF + Milvus Lite 实现向量检索，为用户推荐相似文章。

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

### 推荐 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `POST /api/recommend` | 请求：`{title, content}` | 返回 top-3 相似文章 |
| `POST /api/recommend/add` | 请求：`{title, content, url?, summary?}` | 将文章加入知识库 |

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

- 前端基于 React + Vite + Tailwind，新增页面写在 `frontend/src/pages/`
- 设计参考文件位于 `frontend/design-ref/`，只读不可修改
- 颜色、间距必须使用设计令牌中的值
- 后端新增 API 统一写在 `backend/app.py`
- 发现设计矛盾时回上游讨论，不在下游私自改动

---

## License

MIT
