# 耳行 Web 端组件清单

> 来源：上游设计原型 web.html
> 同步时间：2026-05-04

---

## 布局组件

### SideNavBar
- 宽度：240px，固定左侧
- 背景：#1a1a1a，右边框 #2a2a2a
- 内容：
  - 顶部欢迎语 + Logo（"耳行" + PRO badge）
  - 主导航：新播客 / 全局搜索 / 我的播客(0) / 产出物
  - 探索区：订阅 / 热门
  - 合集区：新合集 + empty state
  - 底部：注册/登录按钮
- 图标：lucide-react（sparkles, search, library, headphones, rss, flame, plus, log-in）
- 交互：hover bg-white/5，active 文字变白

### TopBar
- 当前原型中未显示（零状态页居中布局），但实际应用中应有
- 参考 BibiGPT：搜索框 + 通知/分享/头像

---

## 页面组件

### ZeroStatePage（当前显示的页面）
- 居中内容区，max-w-2xl
- 标题区：badge（支持 AI 双人对话播客 NEW）+ 大标题
- 输入卡片（核心交互）：
  - Tab 切换：链接 / 文本 / 上传 / 探索
  - 输入框：placeholder "粘贴文章链接，支持批量输入..."
  - 底部操作栏：生成设置 / 默认模型 / 快速粘贴
- 快速体验区：两个 pill 链接（示例内容）
- 主按钮："一键生成"（白色 bg，黑色文字，rounded-full）
- 辅助链接：热门内容 / 批量生成

### FeatureBento（底部展示）
- 2 列卡片网格
- 卡片内容：icon + 标题 + 描述
- 当前有两个：拟人化双人对谈 / 高品质音色还原
- **注意**：这是生成工具额外添加的，不在原始 Prompt 中

---

## 通用组件

### InputCard
- 背景 #161618，边框 #2a2a2a，rounded-2xl
- Tab 栏：底部边框区分 active（粉色下划线）
- Textarea：透明背景，placeholder gray
- Footer：左右分栏，小按钮

### PillButton
- rounded-full，bg-white/5，border white/5
- 用于：快速体验链接、filter 标签

### PrimaryButton
- bg-white，text-black，rounded-full
- 大号：px-12 py-4，带 icon
- hover: bg-white/90，active: scale-95

---

## 页面组件（已设计）

### MyPodcastsPage
- 路径：`pages/my-podcasts.html`
- 布局：标题区（左标题 + 右筛选/排序）+ 3 列卡片网格
- 卡片结构：渐变封面区（带时长 badge）+ 标题 + 描述 + 状态标签（已就绪/生成中）+ 时间
- 状态标签：已就绪（brand-pink）、生成中（amber）
- Empty State：图标 + "还没有播客" + 去生成按钮

### SubscriptionPage
- 路径：`pages/subscriptions.html`
- 布局：标题 + 输入卡片（链接输入 + 订阅按钮）+ 列表
- 列表项：平台图标 + 名称 + 平台标签 + 上次生成时间 + 同步状态 + 设置/删除按钮
- 状态：自动同步中（brand-tertiary 绿点）、已暂停（gray）

### GenerationPage
- 路径：`pages/generation.html`
- 布局：居中全页，大头像（小羊/小姜）+ 进度卡片 + 步骤列表 + 操作按钮
- 头像：speaking-ring 动画（脉冲光环），当前说话者高亮
- 进度：渐变进度条 + 百分比 + 拟人化状态文本
- 步骤列表：已完成（check-circle-2 + brand-tertiary）、进行中（loader-2 spin + brand-pink）、未开始（circle + slate-700）
- 操作：后台运行 / 取消生成

### PlayerPage
- 路径：`pages/player.html`
- 布局：顶部信息栏（返回 + 标题 + 操作按钮）+ 左右分栏
- 左栏：双头像（带动画 ring）+ 波形可视化 + 进度条 + 控制按钮（快退/播放/快进）
- 右栏：对话文稿列表，当前段高亮（brand-pink 左边框 + bg-white/5）
- 控制按钮：白色圆形播放键，其余为 ghost 按钮

### DetailPage
- 路径：`pages/detail.html`
- 布局：面包屑 + 标题元信息 + 来源卡片 + 摘要 + 章节大纲 + 操作按钮
- 来源卡片：图标 + 链接 + 访问原文按钮
- 章节大纲：编号圆角方块（当前激活为 brand-pink）+ 标题 + 描述 + 时间范围
- 操作：收听播客（PrimaryButton 白底黑字）、收藏、下载、分享

### SettingsPage
- 路径：`pages/settings.html`
- 布局：分组卡片列表（模型 / 时长 / 音质 / 账号 / 危险操作）
- 模型选择：3 列 option-card（Kimi / DeepSeek / GPT-4o），active 状态 border-brand-pink + bg-brand-pink/5
- 时长选择：5/10/15 分钟，同上 option-card 样式
- 音质：开关 toggle（品牌粉 active）
- 账号：头像 + 名称 + 编辑按钮 + API Key 配置
- 危险操作：红色文字 + 红色边框按钮

### SearchPage
- 路径：`pages/search.html`
- 布局：标题 + 搜索输入卡片 + 按类型分组的结果列表
- 结果分组：播客 / 文章 / 订阅源，每组显示数量
- 播客结果：图标 + 标题 + 平台 · 时长 · 时间 + 播放按钮
- 文章结果：平台标签 + 标题 + 摘要
- 订阅源结果：平台图标 + 名称 + 统计信息

### HotPage
- 路径：`pages/hot.html`
- 布局：标题 + filter pills（全部/科技/商业/文化/生活方式）+ 排名列表
- 排名项：序号（top3 高亮 brand-pink，其余 slate-400）+ 标题 + 标签（精选/热门）+ 摘要 + 收听数/时长/平台 + 播放按钮

### CollectionsPage
- 路径：`pages/collections.html`
- 布局：标题区（左标题 + 右新建合集按钮）+ 2 列合集卡片网格
- 合集卡片：文件夹图标 + 名称 + 播客数量 + 内含播客列表（最多 3 条）+ hover 显示更多按钮
- Empty State：图标 + "还没有合集" + 新建按钮

### HistoryPage
- 路径：`pages/history.html`
- 布局：标题 + 按时间分组的时间线（今天 / 昨天 / 更早）
- 记录项：图标 + 标题 + 播放进度或"已听完" + 平台 + 时间戳 + 播放/重播按钮

### FavoritesPage
- 路径：`pages/favorites.html`
- 布局：标题 + 收藏列表
- 列表项：心形图标（brand-pink）+ 标题 + 平台 · 时长 · 时间 + 播放按钮 + hover 删除按钮
- Empty State：图标 + "还没有收藏" + 去生成链接

### NotesPage
- 路径：`pages/notes.html`
- 布局：标题 + 输入卡片（标题输入 + 内容 textarea + 关联播客 + 保存按钮）+ 笔记列表
- 笔记卡片：标题 + 内容 + 关联播客来源 + 时间 + hover 删除按钮
- Empty State：图标 + "还没有笔记"

### LoginPage
- 路径：`pages/login.html`
- 布局：居中卡片，Logo + 副标题 + 表单 + 第三方登录 + 切换注册/登录
- 表单：邮箱输入（mail icon）+ 密码输入（lock icon）+ 登录按钮
- 第三方：GitHub 登录按钮（白色/5 背景）
- 输入框 focus 状态：border-brand-pink/50

---

## 设计规则

- 暗黑模式唯一，无亮色模式
- 主背景 #0c0c0e，侧边栏 #1a1a1a，卡片 #161618
- 品牌色：pink-500 #ec4899
- 无 emoji，全部 lucide-react SVG
- 无 glow/neon（但当前实现有 glow，需修正）
- 字体：Space Grotesk（英文）+ PingFang SC（中文回退）
