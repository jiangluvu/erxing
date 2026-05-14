# 播刻 TTS 迁移至 Fish Audio 完整记录

## 日期
2026-05-13

## 一、背景与问题

### 1.1 原有方案：edge-tts
- **实现**：直接调用微软 edge-tts 免费接口，通过 SSML 标签控制语调和停顿
- **问题**：
  - 音色机械感强，明显是"机器人在读稿"
  - 情绪控制靠 SSML `prosody` 标签，生硬不自然
  - 男女声区分仅靠固定语音包（Yunxi/Xiaoxiao），无个性
- **结论**：无法满足播客"伴随式收听"对自然度的要求

### 1.2 中间方案：Azure 语音服务
- **调研**：用户购买了 Azure CSP 代理账号，尝试了 Azure TTS
- **问题**：
  - 需要 SSML `express-as` 标签控制情绪，中文支持有限
  - 多音字、英文缩写朗读错误（如 GDP 读成"gdp"而非"G-D-P"）
  - 成本较高，且注册流程复杂
- **结论**：比 edge-tts 好，但仍不够自然，且成本和接入门槛高

---

## 二、调研过程

### 2.1 候选方案对比

| 方案 | 自然度 | 音色一致性 | 中文支持 | 成本 | 接入难度 | 结论 |
|------|--------|-----------|---------|------|---------|------|
| edge-tts | 低 | 高 | 好 | 免费 | 低 | 音色机械，放弃 |
| Azure TTS | 中 | 高 | 中 | 中高 | 中 | 情绪生硬，放弃 |
| **Fish Audio** | **高** | **中（可修复）** | **好** | **中** | **低** | **选中** |
| MiniMax | 未知 | 未知 | 未知 | 未知 | 未知 | 未调研 |
| 讯飞/火山 | 未知 | 未知 | 未知 | 未知 | 未知 | 未调研 |

### 2.2 为什么选 Fish Audio
1. **自然度天花板高**：基于 Fish Speech 开源模型，生成式 TTS，语气接近真人朗读
2. **中文优化好**：社区有大量中文语音模型，对中文语调和多音字处理更自然
3. **情绪控制自然**：通过自然语言标签 `[excited]`、`[whispering]`、`[slow]` 控制，无需 SSML
4. **零样本克隆**：支持上传 10-30 秒参考音频克隆任意声线
5. **成本低**：$1 可生成约 10-15 分钟音频，播客场景可接受

### 2.3 Fish Audio 核心特性验证

**验证 1：情感标签效果**
- 测试了 `[excited]`、`[whispering]`、`[slow]` 等标签
- 结论：标签有效，能明显改变语调和语速，但音色会随标签轻微变化

**验证 2：speed 参数影响**
- 发现 `speed` 参数不仅改变语速，还会改变音色（共振峰偏移）
- 结论：不能用 speed 区分"标准"和"点评"等同音色不同语速的预设

**验证 3：默认音色稳定性**
- 同一段文本多次调用，返回音频大小不同（226KB vs 232KB）
- 同一段长文本内，前后音色不一致
- 结论：Fish Audio 默认内置音色有底层随机性，不可用于生产环境

---

## 三、技术方案演进

### 阶段 1：基础接入（已完成）
- 新建 `tts_engine.py`，封装 Fish Audio `/v1/tts` API
- 支持默认音色（不传参考音频）和 zero-shot 克隆（传 `reference_audio`）
- 实现音频拼接、静音生成、SSML 清洗等基础功能

### 阶段 2：音色漂移排查（已完成）
**问题发现**：同预设不同文本音色完全不同，像换了一个人。

**排查路径**：
1. **怀疑参考音频太短**：从 7 秒延长到 30 秒 → 无效
2. **怀疑 speed 影响**：统一 speed=1.0 → 有改善，但未根治
3. **怀疑 API 参数缺失**：补上 `model: s2-pro` 请求头、`temperature: 0.1` → 同一段文本内仍有漂移
4. **验证 API 确定性**：相同参数调用两次，返回文件大小不同 → 确认模型本身非确定性

**关键结论**：生成式 TTS 的潜空间采样有固有随机性，`temperature=0.1` 仍无法做到 100% 一致。

### 阶段 3：reference_id 预创建 Voice（当前方案）
**方案切换**：从 zero-shot `reference_audio` 切换到预创建 `reference_id`

**逻辑**：
- Fish Audio 网页端上传参考音频 → 训练成固定 Voice Model → 拿到 Model ID
- API 调用时传 `reference_id: "xxx"` 而非 `reference_audio: "base64..."`
- 预创建模型权重已固定，每次调用从固定潜空间出发，音色稳定性大幅提升

**验证结果**：
- 同 Voice Model、不同文本，音色高度一致
- 用户确认："稳定了，同 voice 音色一致"

---

## 四、改动详情

### 4.1 `erxing/backend/tts_engine.py`

**新增功能**：
- `synthesize_turn()`：支持 `reference_id` 和 `reference_audio_path` 两种引用方式
- `generate_podcast()`：新增 `male_ref_id` / `female_ref_id` 参数
- 5 种男声预设映射（`_EMOTION_MAP` + `_EMOTION_SPEED`）

**关键修复**：
```python
# 修复前（音色漂移）
headers = {"Authorization": "Bearer ...", "Content-Type": "application/json"}
payload = {"text": text, "speed": speed, "format": "mp3"}

# 修复后（音色稳定）
headers = {"Authorization": "Bearer ...", "Content-Type": "application/json", "model": "s2-pro"}
payload = {
    "text": text,
    "format": "mp3",
    "sample_rate": 44100,
    "temperature": 0.1,      # 大幅降低随机性
    "top_p": 0.7,
    "prosody": {"speed": speed, "volume": 0, "normalize_loudness": True},
    "reference_id": voice_id,  # 预创建 Voice，锁定音色
}
```

### 4.2 `erxing/backend/app.py`

**新增配置**：
```python
MALE_VOICE_ID = os.environ.get("FISH_MALE_VOICE_ID", "639cdf5253a24b50a18cbdb726acce15")
FEMALE_VOICE_ID = os.environ.get("FISH_FEMALE_VOICE_ID", "")
```

**修改调用点**：
- `tts_script()`：传入 `male_ref_id=MALE_VOICE_ID`
- `_tts_script_segment()`：传入 `male_ref_id=MALE_VOICE_ID`

---

## 五、当前配置

```python
# Fish Audio API
API_KEY = "6797c57bffe4459dbfad51b01e20ab65"
API_URL = "https://api.fish.audio/v1/tts"
MODEL = "s2-pro"
TEMPERATURE = 0.1

# Voice Model IDs（fish.audio 预创建）
MALE_VOICE_ID = "639cdf5253a24b50a18cbdb726acce15"   # 用户上传的男声
FEMALE_VOICE_ID = "a71b052094fa4505967e262b8cb7d0a6" # 用户上传的女声
```

---

## 六、已知限制与待办

### 6.1 限制
1. **5 个男声预设共用同一个 Voice Model**
   - 标准/点评/沉思/磁性/青年 均使用同一男声 ID
   - 差异仅靠 `speed` + `[slow]/[whispering]/[excited]` 标签
   - 如需 5 种独立声线，需额外创建 4 个 Voice Model

2. **女声未配置**
   - `FEMALE_VOICE_ID` 为空，女声仍用 Fish Audio 默认音色
   - 默认女声有漂移风险，需上传女声参考音频创建 Voice Model

3. **成本**
   - Fish Audio 按字符计费，长文本播客成本需监控
   - 当前用户余额 $1，约可生成 10-15 分钟音频

### 6.2 已完成里程碑
- [x] **2026-05-13**：男声 Voice Model 配置完成，音色锁定验证通过
- [x] **2026-05-13**：女声 Voice Model 配置完成（ID: `a71b052094fa4505967e262b8cb7d0a6`）
- [x] **2026-05-13**：男女声全流程端到端测试通过（8 轮对话，68.3 秒，音色稳定）
- [x] **2026-05-13**：用户确认效果满意，决定先用一个男声 Voice 跑通生产流程

### 6.3 待办（后续补充）
- [ ] **5 个男声预设独立声线**：当前共用同一个 Voice Model，后续可上传 4 段不同参考音频到 fish.audio，创建独立 Voice Model（标准/点评/沉思/磁性/青年各一个）
- [ ] **成本监控**：Fish Audio 按字符计费，需在生产环境中加入用量统计和余额预警
- [ ] **异常降级**：Fish Audio API 失败时（余额不足/网络错误），自动 fallback 到 edge-tts 或返回错误提示
- [ ] **缓存机制**：相同文本+相同预设的音频可缓存复用，减少 API 调用成本
- [ ] **多音字/英文优化**：Fish Audio 对英文缩写（如 GDP、AI）的朗读质量需进一步验证

---

## 七、参考链接与文件

- Fish Audio 官网：https://fish.audio
- 用户上传的男声 Voice Model：
  `https://fish.audio/app/text-to-speech/?modelId=639cdf5253a24b50a18cbdb726acce15&version=s2-pro`
- 用户上传的女声 Voice Model：
  `https://fish.audio/app/text-to-speech/?modelId=a71b052094fa4505967e262b8cb7d0a6&version=s2-pro`
- 参考音频录制文本：`erxing/backend/ref_texts.txt`
- 测试输出目录：`erxing/backend/benchmark_output/`

---

## 八、关键决策记录

| 决策点 | 选项 | 选择 | 原因 |
|--------|------|------|------|
| TTS 引擎 | edge-tts / Azure / Fish Audio | Fish Audio | 自然度最高，中文支持好 |
| 音色锁定 | zero-shot / pre-trained Voice | pre-trained Voice | zero-shot 无法锁定音色 |
| 参考方式 | `reference_audio` / `reference_id` | `reference_id` | reference_audio 漂移严重 |
| speed 用法 | 区分预设 / 统一 1.0 | 保留差异（1.0/1.05/0.9/0.95/1.1） | 用户确认 speed 可区分语气 |
| 情绪标签 | SSML / 自然语言 | 自然语言 | Fish Audio 不支持 SSML |
| 模块组织 | 改 app.py / 新建 tts_engine.py | 新建 tts_engine.py | 避免改动 1100+ 行 app.py，节省上下文 |

---

## 九、技术实现详情

### 9.1 模块架构与调用链路

```
frontend (播刻对话脚本)
    ↓ POST /api/tts
app.py::tts_script()
    ↓ import generate_podcast
tts_engine.py::generate_podcast(script, male_ref_id, female_ref_id)
    ├── 遍历 script 每一项
    │   ├── clean_ssml(text)          # 去除 SSML 标签
    │   ├── _polish_text(text)        # 断长句、清理标点
    │   ├── _inject_emotion_tag()     # 注入 [excited]/[slow]/[whispering]
    │   ├── _EMOTION_SPEED[emotion]   # 查表获取 speed
    │   └── synthesize_turn()         # 调用 Fish Audio API
    │       ├── 组装 headers（含 model: s2-pro）
    │       ├── 组装 payload（含 temperature: 0.1, prosody.speed）
    │       ├── 优先传 reference_id，否则 fallback 到 reference_audio
    │       └── requests.post(API_URL, ...)
    ├── _compute_pause() + _generate_silence()  # 句间停顿
    └── concat_podcast()              # ffmpeg concat 拼接
        ↓
    返回 podcast.mp3
```

### 9.2 `tts_engine.py` 核心函数

#### `synthesize_turn(text, output_path, reference_audio_path, reference_id, speed)`
- **作用**：调用 Fish Audio `/v1/tts` 合成单句语音
- **参数优先级**：`reference_id` > `reference_audio_path` > 默认内置音色
- **关键 headers**：`model: s2-pro`（必须，否则可能回退到旧模型）
- **关键 payload**：
  ```python
  {
      "text": text,
      "format": "mp3",
      "sample_rate": 44100,
      "temperature": 0.1,          # 降低随机性
      "top_p": 0.7,
      "prosody": {
          "speed": speed,          # 0.9 ~ 1.1
          "volume": 0,
          "normalize_loudness": True,
      },
      "reference_id": voice_id,    # 预创建 Voice Model
  }
  ```

#### `generate_podcast(script, output_path, male_ref, female_ref, male_ref_id, female_ref_id)`
- **作用**：将播客脚本转成完整 MP3
- **流程**：
  1. 遍历 `script`（每项含 `speaker`, `text`, `emotion`）
  2. 根据 `speaker` 选择 `male_ref_id` 或 `female_ref_id`
  3. 根据 `emotion` 查 `_EMOTION_MAP` 和 `_EMOTION_SPEED`
  4. 每句合成后插入静音（`_generate_silence`）
  5. 用 `ffmpeg concat` 拼接为最终 MP3

#### `clean_ssml(text)`
- 去除所有 SSML 标签（`break`, `emphasis`, `prosody`, `say-as`, `speak`, `voice`）
- 将 `[停顿]` 替换为中文逗号，去除 `[轻声]...[/轻声]`
- **原因**：Fish Audio 不支持 SSML，标签会被直接朗读

#### `_polish_text(text)`
- 清理连续逗号/句号（`，，` → `，`）
- 超长句（>35 字无标点）在"是/的/了"后插入逗号，帮助模型自然断句

#### `_compute_pause(text)`
- 根据句尾标点计算停顿时长：
  - 问号结尾：0.6s
  - 感叹号结尾：0.4s
  - 过渡词（总之/所以/你看）：0.5s
  - 句号结尾：0.35s
  - 默认：0.25s

### 9.3 5 种男声预设配置

| 预设 | 情感标签 | speed | 适用场景 | Fish Audio 实际效果 |
|------|---------|-------|---------|-------------------|
| 标准 | 无 | 1.0 | 开场白、陈述事实 | 正常语速，无情绪标记 |
| 点评 | 无 | 1.05 | 数据解读、观点输出 | 略快，节奏紧凑 |
| 沉思 | `[slow]` | 0.9 | 提出疑问、深度思考 | 语速放慢，低沉 |
| 磁性 | `[whispering]` | 0.95 | 深夜电台、感性分析 | 耳语感，气息明显 |
| 青年 | `[excited]` | 1.1 | 兴奋追问、热点讨论 | 上扬语调，活力感 |

**注**：当前 5 个预设共用同一个 `MALE_VOICE_ID`，差异仅靠 speed + 标签实现。

### 9.4 `app.py` 集成方式

#### 全局配置
```python
from tts_engine import generate_podcast

MALE_VOICE_ID = os.environ.get("FISH_MALE_VOICE_ID", "639cdf5253a24b50a18cbdb726acce15")
FEMALE_VOICE_ID = os.environ.get("FISH_FEMALE_VOICE_ID", "")
```

#### `tts_script(script)` —— 完整播客 TTS 入口
```python
def tts_script(script, voice_map=None):
    out_path = Path(tempfile.mkdtemp(prefix="boke_")) / "podcast.mp3"
    generate_podcast(
        script,
        output_path=str(out_path),
        male_ref_id=MALE_VOICE_ID or None,
        female_ref_id=FEMALE_VOICE_ID or None,
    )
    return str(out_path)
```

#### `_tts_script_segment(script, tag)` —— 开场白/分段 TTS
```python
def _tts_script_segment(script, tag="seg", voice_map=None):
    out_path = Path(tempfile.mkdtemp(prefix=f"boke_{tag}_")) / f"{tag}.mp3"
    generate_podcast(
        script,
        output_path=str(out_path),
        male_ref_id=MALE_VOICE_ID or None,
        female_ref_id=FEMALE_VOICE_ID or None,
    )
    return str(out_path)
```

### 9.5 API 请求/响应示例

**请求**（标准预设）：
```http
POST https://api.fish.audio/v1/tts
Authorization: Bearer 6797c57bffe4459dbfad51b01e20ab65
Content-Type: application/json
model: s2-pro

{
    "text": "大家好，欢迎收听本期播客。",
    "reference_id": "639cdf5253a24b50a18cbdb726acce15",
    "format": "mp3",
    "sample_rate": 44100,
    "temperature": 0.1,
    "top_p": 0.7,
    "prosody": {"speed": 1.0, "volume": 0, "normalize_loudness": true}
}
```

**响应**：
- Status: 200
- Content-Type: audio/mpeg
- Body: MP3 音频二进制流

### 9.6 文件依赖关系

```
erxing/backend/
├── app.py                     # Flask 主程序，调用 tts_engine
│   └── from tts_engine import generate_podcast
│   └── MALE_VOICE_ID / FEMALE_VOICE_ID 配置
│
├── tts_engine.py              # 核心 TTS 引擎（独立模块）
│   ├── synthesize_turn()      # 单句合成
│   ├── generate_podcast()     # 完整播客拼接
│   ├── clean_ssml()           # SSML 清洗
│   ├── _polish_text()         # 文本润色
│   ├── _compute_pause()       # 停顿计算
│   ├── _generate_silence()    # ffmpeg 生成静音
│   └── concat_podcast()       # ffmpeg 拼接音频
│
├── benchmark_output/          # 测试输出目录
│   ├── ref_voice_standard.mp3 # 标准男声参考音频
│   ├── ref_voice_youth.mp3    # 青年男声参考音频
│   ├── ref_standard.mp3       # 从旧音频截取的参考片段
│   ├── ref_youth.mp3
│   └── fish_presets_dialogue.mp3  # 5 预设对话测试
│
├── ref_texts.txt              # 参考音频录制文本
│
└── test_*.py                  # 各类测试脚本
    ├── test_app_fish.py       # 端到端播客测试
    ├── test_presets.py        # 5 预设单句测试
    ├── test_presets_dialogue.py  # 5 预设对话测试
    ├── test_reference_audio.py   # reference_audio 锁定测试
    ├── test_user_voice.py        # reference_id 锁定测试
    └── gen_ref_voices.py         # 纯净参考音频生成
```

### 9.7 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `FISH_API_KEY` | 是 | - | Fish Audio API Key |
| `FISH_API_URL` | 否 | `https://api.fish.audio/v1/tts` | API 地址 |
| `FISH_MALE_VOICE_ID` | 否 | `639cdf5253a24b50a18cbdb726acce15` | 男声 Voice Model ID |
| `FISH_FEMALE_VOICE_ID` | 否 | `""` | 女声 Voice Model ID |
