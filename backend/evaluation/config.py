"""Evaluation 系统配置：常量、路径、维度枚举。"""

from pathlib import Path

# ── 路径 ──
EVAL_DIR = Path(__file__).parent
BASE_DIR = EVAL_DIR.parent
BENCHMARK_DIR = EVAL_DIR / "data"
RESULTS_DIR = EVAL_DIR / "results"
LOGS_PATH = BASE_DIR / "logs.jsonl"

# ── 模型 ──
ZHI_MODEL = "deepseek-v4-flash"       # 生成模型
EVAL_MODEL = "gpt-4o-mini"            # 评测模型

# ── Layer 3: A/B 对比维度 ──
class Layer3Dimensions:
    OVERALL_NATURALNESS = "overall_naturalness"       # 整体自然度
    CAR_SCENE_FIT = "car_scene_fit"                   # 播客收听场景适配
    INFO_DENSITY = "info_density_reasonableness"      # 信息密度合理性

# ── Layer 4: AI 自动评测维度 ──
class Layer4Dimensions:
    CONTENT_ACCURACY = "content_accuracy"             # 内容准确性
    DIALOGUE_NATURALNESS = "dialogue_naturalness"     # 对话自然度
    SCENE_FIT = "scene_fit"                           # 场景适配

# ── Layer 6: 人工评测维度 ──
class Layer6Dimensions:
    SOUNDS_REAL = "sounds_like_real_conversation"     # 像真实对话
    SUITABLE_CAR = "suitable_for_car"                 # 适合播客收听
    INFO_DENSITY = "info_density_reasonableness"      # 信息密度合理
    WILLING_FINISH = "willing_to_finish"              # 愿意听完

# ── 阈值 ──
AB_SIGNIFICANCE_THRESHOLD = 0.60  # A/B 胜率显著性阈值
