# Azure 官方 API 最小验证方案

**目标**：在不修改播刻任何生产代码的前提下，用最小成本验证 Azure 官方 API 相对于 edge-tts 的效果提升。
**预期耗时**：30 分钟（含申请 Key）
**预期成本**：~0.1 元（测试 8 句对话）

---

## 一、准备工作

### 1.1 申请 Azure Speech Service（免费额度足够验证）

1. 访问 [Azure 门户](https://portal.azure.com/)，注册/登录账号
2. 创建 Resource Group → 搜索 "Speech" → 创建 "Speech" 资源
3. 定价层选择 **Free F0**（每月 50 万字符免费，足够验证）
4. 创建完成后，进入资源 → **Keys and Endpoint** → 复制 `Key1` 和 `Location/Region`

> 如果没有 Azure 账号，可以用微软账号登录，首次注册有 12 个月免费额度 + $200 信用额度。

### 1.2 本地安装依赖

在 `erxing/backend/` 目录下执行：

```bash
pip install azure-cognitiveservices-speech
```

如果只想验证不安装，tts_benchmark.py 会在运行时提示缺少依赖并跳过 Azure 引擎。

---

## 二、验证步骤

### 2.1 运行 Benchmark 对比测试

`tts_benchmark.py` 已内置 Azure 支持，无需修改任何代码。

**命令**：

```bash
cd erxing/backend
python tts_benchmark.py --engines edge,azure --azure-key YOUR_KEY --azure-region YOUR_REGION
```

**输出**：
```
benchmark_output/
├── edge_tts_podcast.mp3   ← edge-tts 基准
├── azure_podcast.mp3      ← Azure 官方（15种风格）
└── report.json            ← 耗时/文件大小对比
```

### 2.2 测试脚本说明

benchmark 使用同一段 8 轮对话脚本（`TEST_SCRIPT`），覆盖以下场景：

| 轮次 | 说话人 | 情绪 | 特殊标记 |
|------|--------|------|---------|
| 1 | 女声 | 疑问 | 数据提问 |
| 2 | 男声 | 平静 | 百分比、GDP 缩写 |
| 3 | 女声 | 疑问 | 反问句 |
| 4 | 男声 | 沉思 | `[停顿]`、`[轻声]...[/轻声]` |
| 5 | 女声 | 兴奋 | 惊叹 |
| 6 | 男声 | 兴奋 | 长句 |
| 7 | 女声 | 疑问 | 选择问 |
| 8 | 男声 | 平静 | 列举 + 停顿 |

**Azure 专属能力验证点**：
- `mstts:express-as style="cheerful"`（兴奋情绪）
- `mstts:express-as style="serious"`（沉思情绪）
- `styledegree="1.5"`（情感强度增强）
- 与 edge-tts 相同的 SSML 基础能力（break/emphasis/prosody）

### 2.3 人工听感对比清单

戴上耳机，A/B 对比两个 MP3，重点听：

| 检查项 | edge-tts | Azure | 差异明显？ |
|--------|---------|-------|-----------|
| 女声疑问句的语气 | 基准 | `chat`/`cheerful` 风格 | |
| 男声沉思时的沉重感 | 基准 | `serious` 风格 + `styledegree` | |
| "GDP" 是否读成字母 | 基准 | 同（SSML 相同） | |
| "35.6%" 的强调感 | 基准 | 同（SSML 相同） | |
| `[停顿]` 处的停顿 | 基准 | 同（SSML 相同） | |
| 整体情感丰富度 | 单调 | 是否有明显风格区分 | |
| 拼接感 | 有 | 是否有改善（虽然仍是拼接式） | |

### 2.4 快速试听命令（macOS/Linux）

```bash
# 先听 edge-tts
ffplay benchmark_output/edge_tts_podcast.mp3

# 再听 Azure
ffplay benchmark_output/azure_podcast.mp3
```

Windows 直接用播放器打开即可。

---

## 三、验证后的决策分支

```
听完对比后
│
├─ Azure 明显优于 edge-tts
│   └─ 决策：正式接入 Azure 作为平台默认引擎
│       └─ 下一步：在 tts_benchmark.py 基础上，写接入 backend/app.py 的 PR
│
├─ Azure 和 edge-tts 差别不大
│   └─ 决策：拼接式架构已到天花板
│       └─ 下一步：跳过 Azure，直接部署 Fish Speech 验证端到端效果
│
└─ Azure 某些风格好听，某些不好听
    └─ 决策：保留风格选择，让创作者自选
        └─ 下一步：平台提供"男声风格""女声风格"下拉菜单
```

---

## 四、如果 Benchmark 脚本有问题

### 4.1 常见错误

**错误 1**：`ImportError: azure-cognitiveservices-speech not installed`
- 解决：`pip install azure-cognitiveservices-speech`

**错误 2**：`SynthesizingAudioCompleted` 失败
- 可能原因：SSML 格式错误、region 填错、Key 无效
- 调试：在 `synthesize_azure` 函数末尾加 `print(ssml)` 查看生成的 SSML

**错误 3**：Windows 下 ffmpeg 找不到
- 解决：确保 ffmpeg 在 PATH 中，或把 ffmpeg.exe 放到 `backend/` 目录

### 4.2 最小化手动测试（如果 benchmark 跑不通）

可以直接用以下 Python 脚本测试单句 Azure 效果：

```python
import azure.cognitiveservices.speech as speechsdk

key = "YOUR_KEY"
region = "YOUR_REGION"

speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
speech_config.speech_synthesis_voice_name = "zh-CN-YunxiNeural"

ssml = (
    '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
    'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="zh-CN">'
    '<voice name="zh-CN-YunxiNeural">'
    '<mstts:express-as style="cheerful" styledegree="1.5">'
    '你看，2024年新能源汽车销量突破了950万辆，这个数据你注意到没？'
    '</mstts:express-as>'
    '</voice></speak>'
)

audio_config = speechsdk.audio.AudioOutputConfig(filename="azure_test.wav")
synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
result = synthesizer.speak_ssml_async(ssml).get()

if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
    print("成功生成 azure_test.wav")
else:
    print(f"失败: {result.reason}")
```

---

## 五、验证范围边界

**本次验证明确不做的**：
- ❌ 不修改 `backend/app.py` 任何一行代码
- ❌ 不改前端、不改 API 接口
- ❌ 不部署 GPU、不碰 Fish Speech
- ❌ 不做长文章测试（只测 8 轮对话 benchmark）

**本次验证要做的**：
- ✅ 确认 Azure 15 种风格在中文播客场景下的实际听感差异
- ✅ 确认现有 SSML 规则（停顿/强调/轻声）在 Azure 上是否兼容
- ✅ 确认成本是否在预期范围内

---

## 六、预期产出

验证完成后，你应该能回答：
1. Azure 的 `cheerful`/`serious`/`chat` 风格在中文双人播客中是否自然？
2. `styledegree=1.5` 是否会让声音过于夸张？
3. 现有 edge-tts 优化迁移到 Azure 的成本是否真的很小？

这些答案将直接决定下一步是"接入 Azure"还是"跳过 Azure 直接上 Fish Speech"。
