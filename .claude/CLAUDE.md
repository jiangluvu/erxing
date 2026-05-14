# 播刻工程规则

## 全局交互规则（不可违反）
- 每次回复结束时必须调用 AskUserQuestion 提问，不得让对话看起来已结束
- 用户没明确说"完成了""可以了""结束"时，必须继续推进或征求意见
- 如果用户指出违反规则，立即停下来确认并修正，不要辩解

## 上游设计参考
- 设计文件位于 `frontend/design-ref/`（只读，不可修改）
- 实现时必须对照：
  - `web.html` → 桌面端界面原型
  - `design-tokens.json` → 颜色/间距/字体令牌
  - `components.md` → 组件清单和交互说明
- 颜色、间距必须使用设计令牌中的值，不可随意写死

## 技术栈
- 前端：单页 HTML（`frontend/index.html`），原生 CSS + 原生 JS
- 后端：Python Flask（`backend/app.py`）
- 矢量/符号图标使用 Unicode emoji（网页组件中可用）
- 存储：后端 JSONL 文件 + localStorage

## 工作流
1. 读取 `frontend/design-ref/` 了解当前设计
2. 在 `frontend/index.html` 中对照实现（单文件，含 CSS + HTML + JS）
3. 后端新增 API 写在 `backend/app.py`
4. 如果发现设计有矛盾或无法实现，回上游讨论，不在下游私自改动设计
5. 所有改动先在本地测试，用户同意后再部署

## 禁止事项
- 不得直接修改 `frontend/design-ref/` 中的文件
- 不得随意更改设计令牌中的颜色/字体值
