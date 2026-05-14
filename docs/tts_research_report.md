# TTS 竞品深度调研报告

**调研日期**：2026-05-11
**调研范围**：中文双人播客场景下的 TTS 引擎选型
**核心问题**：当前 edge-tts 拼接架构的"AI感"能否通过换引擎解决？成本与效果如何权衡？

---

## 一、调研背景

播刻当前架构：LLM 生成对话文本 → edge-tts 逐句合成 → ffmpeg 拼接 → MP3。

已完成优化：停顿插入、SSML 强调、情绪 prosody、角色稳定性、口语化标记。

**仍未解决的痛点**：
1. 拼接感——每句话独立合成，语气不连续
2. 无笑声/叹息/呼吸声——真实播客中大量存在
3. 情绪表达有限——只有 rate/pitch 两种维度

---

## 二、候选方案全景对比

| 维度 | edge-tts | Azure 官方 | 豆包 Seed-TTS | Fish Speech | ChatTTS | CosyVoice 2 |
|------|----------|------------|---------------|-------------|---------|-------------|
| **类型** | 在线 API | 在线 API | 在线 API | 开源/本地 | 开源/本地 | 开源/本地 |
| **底层引擎** | Azure Edge | Azure Neural | 自研 Seed-TTS | Fish Audio S2 | 自研 | 阿里 |
| **月成本** | 0 元 | ~100 元/100万字符 | ~500 元/100万字符 | GPU 电费 | GPU 电费 | GPU 电费 |
| **中文质量** | 好 | 好 | 优秀 | 优秀(WER 0.54%) | 优秀 | 优秀 |
| **笑声** | ❌ | ❌(英文有) | ❌(未公开) | ✅ `[laugh]` | ✅ `[laugh]` | ✅ `[laughter]` |
| **叹息/呼吸** | ❌ | ❌ | ❌ | ✅ `[sigh]` `[breath]` | ✅ `[uv_break]` | ✅ `[breath]` |
| **单次多角色** | ❌ | ❌ | ❌ | ✅ `<\|speaker:0\|>` | ⚠️ 有限 | ❌ |
| **拼接感** | 明显 | 明显 | 明显 | **无** | 较弱 | 较弱 |
| **控制粒度** | 高(SSML) | 中(15种风格) | 中(情感指令) | 中(标签) | 中(标记) | 中(指令) |
| **部署难度** | 极低 | 低 | 低 | **高**(需GPU) | 中(4GB显存) | 中 |
| **稳定性** | 高 | 高 | 高 | 中(自回归波动) | 中(可能变声) | 高 |
| **商用授权** | 灰色* | ✅ 官方 | ✅ 官方 | ✅ Apache-2.0 | 待确认 | ✅ Apache-2.0 |

> *edge-tts 为非官方封装，底层调用微软服务，大量商用存在潜在协议风险。

---

## 三、各方案详细分析

### 3.1 edge-tts（当前方案）

**优点**：零成本、接入极简、SSML 控制粒度最高（break/emphasis/prosody 全支持）。

**缺点**：拼接式架构先天有机械感；无笑声/非语言声音；情感只有 rate/pitch 两维。

**适用阶段**：MVP 验证、低成本跑量、对自然度要求不极致的场景。

---

### 3.2 Azure 官方 TTS

与 edge-tts 是**同一底层引擎**，但通过官方 SDK 可解锁额外能力。

**新增能力**：
- `mstts:express-as`：15+ 中文风格（`chat`, `cheerful`, `angry`, `sad`, `gentle` 等）
- `styledegree`：情感强度调节（0.01~2.0）
- HD 语音（DragonHD）：更丰富的情感维度
- 英文 `[laughter]` 标签（中文不支持）

**中文声线风格支持**：

| 声线 | 可用风格 |
|------|---------|
| `zh-CN-YunxiNeural`（男声）| `chat`, `cheerful`, `angry`, `sad`, `serious`, `embarrassed`, `depressed` |
| `zh-CN-XiaoxiaoNeural`（女声）| `chat`, `cheerful`, `angry`, `sad`, `gentle`, `affectionate`, `lyrical` |

**改造成本**：极小。edge-tts 和 Azure 官方是同一引擎，只需换 SDK + 加鉴权。

**月成本估算**：$15/100万字符 ≈ 100元/100万字符。

**关键局限**：仍然是**拼接式**，无法解决笑声和拼接感。

---

### 3.3 豆包 / 火山引擎 Seed-TTS

**播客专用 API**：`wss://openspeech.bytedance.com/api/v3/sami/podcasttts`
- action=0：输入文本自动总结生成双人播客（黑盒）
- action=3：传入 `nlp_texts` 自定义对话直接合成（单轮≤300字符，总长≤10000字符）

**大模型语音合成（Seed-TTS 2.0）**：
- 情感指令：`<整体情绪：生气，语气：吵架>`
- 四种基础情绪：愤怒、开心、悲伤、惊讶
- 流式首包 <300ms

**定价**：大模型语音合成 5元/万字符。

**关键局限**：
- 公开文档**未明确支持笑声**
- 播客 API 的 action=3 仍然是**逐句合成**（需传入 speaker+text 列表），本质还是拼接
- 黑盒不可控，丢失现有 SSML 优化

---

### 3.4 Fish Speech（Fish Audio S2）

**开源项目**：https://github.com/fishaudio/fish-speech，28K stars。

**核心突破**：
1. **非语言声音**：`[laugh]`, `[chuckle]`, `[sigh]`, `[inhale]`, `[exhale]`, `(breath)`, `(cough)`
2. **情感标签**：15,000+ 种，词级控制，`(angry)`, `(sad)`, `(excited)`, `[whisper]`
3. **单次推理多角色对话**：`<|speaker:0|>`, `<|speaker:1|>` 一次生成完整双人音频
4. **中文 WER**：0.54%

**部署需求**：
- GPU：4GB+ 显存
- 框架：SGLang 推理引擎
- 模型：Fish Audio S2 Pro

**架构影响**：
- 不再逐句合成 + ffmpeg 拼接
- LLM 生成文本 → 转换为 Fish 格式（speaker 标记 + 情感标签）→ 单次推理 → 完整音频
- 现有 SSML/prosody/停顿优化**全部失效**

**稳定性风险**：自回归模型可能中途变声，建议多次采样选最佳。

---

### 3.5 ChatTTS

**开源项目**：https://github.com/2noise/ChatTTS，专为对话场景优化。

**特色标记**：
- `[laugh]`, `[laugh_n]`（n=0-2）
- `[break_n]`, `[uv_break]`
- `[oral_n]` 口语化程度

**问题**：自回归模型稳定性不足，可能出现说话人中途变化。

**与 Fish Speech 对比**：Fish 在多角色和稳定性上更优。

---

### 3.6 CosyVoice 2（阿里开源）

**开源项目**：https://github.com/FunAudioLLM/CosyVoice，Apache-2.0 许可。

**能力**：`[laughter]`, `[breath]`，自然语言情感指令，18 种方言，首包 150ms。

**优势**：阿里背书，可商用，中文表现稳定。

**劣势**：不支持单次多角色推理，仍需逐句合成。

---

## 四、技术本质：为什么拼接式永远有"AI感"？

| 维度 | 拼接式（edge-tts/Azure/豆包） | 端到端（Fish/Dia/NotebookLM） |
|------|------------------------------|------------------------------|
| **生成单元** | 单句话独立生成 | 整段对话一次性生成 |
| **上下文感知** | 无——TTS 不知道上一句是什么 | 有——模型在潜在空间中看到全文 |
| **语气连续性** | 靠 SSML/prosody 硬凑 | 自然涌现 |
| **笑声/呼吸** | 不支持（无声学层面涌现） | 支持（在潜在空间直接生成） |
| **两人互动感** | 轮流念稿 | 真实对话节奏（抢话、重叠、回应） |

**结论**：只要架构是"逐句合成再拼接"，无论换哪个商业 API（Azure/豆包/讯飞），都无法根本解决 AI 感。**只有端到端模型能破局。**

---

## 五、决策矩阵

| 优先级 | 方案 | 改造成本 | 效果提升 | 风险 | 建议 |
|--------|------|---------|---------|------|------|
| **短期** | Azure 官方 API | 极小 | 中（15种风格，情感更丰富） | 低 | **推荐先做**，边际收益最高 |
| **中期** | Fish Speech 本地 | 大 | **极高**（笑声+无拼接感） | 中（需GPU+稳定性） | 验证效果后决定是否迁移 |
| **观望** | 豆包播客 API | 大 | 未知（黑盒，可能丢失优化） | 高 | 暂不投入 |
| **备选** | CosyVoice 2 | 中 | 高（笑声+中文稳定） | 低 | 如果 Fish 部署困难，选这个 |

---

## 六、测试建议

搭建最小对比测试：用**同一段对话脚本**，分别用以下引擎合成：
1. edge-tts（基准）
2. Azure 官方（`cheerful`/`chat` 风格）
3. Fish Speech（本地或在线，如已部署）
4. CosyVoice 2（本地或在线，如已部署）

对比维度：自然度、情感表现力、笑声/非语言声音、拼接感、延迟。

---

## 七、参考资料

- [Azure SSML 语音与音效文档](https://learn.microsoft.com/zh-cn/azure/ai-services/speech-service/speech-synthesis-markup-voice)
- [Azure HD 高保真语音](https://learn.microsoft.com/zh-cn/azure/ai-services/speech-service/high-definition-voices)
- [豆包语音-播客API文档](https://www.volcengine.com/docs/6561/1668014)
- [火山引擎TTS计费说明](https://www.volcengine.com/docs/6561/1359370)
- [Fish Speech GitHub](https://github.com/fishaudio/fish-speech)
- [ChatTTS GitHub](https://github.com/2noise/ChatTTS)
- [CosyVoice GitHub](https://github.com/FunAudioLLM/CosyVoice)
- [Seed-TTS 论文](https://arxiv.org/html/2406.02430v1)
