import { Bot, Clock, Volume2, ArrowLeft, BarChart3 } from "lucide-react";
import { useAppStore } from "../store";

const models = [
  { id: "deepseek-v4",       label: "DeepSeek V4",         tag: "DeepSeek",  desc: "默认模型，深度推理，长文表现最佳" },
  { id: "deepseek-v4-flash", label: "DeepSeek V4 Flash",   tag: "DeepSeek",  desc: "轻量快速，适合短文本" },
  { id: "gpt-4o",            label: "GPT-4o",              tag: "OpenAI",    desc: "创意丰富，对谈更生动" },
  { id: "gpt-4o-mini",       label: "GPT-4o Mini",         tag: "OpenAI",    desc: "轻量版，性价比高" },
  { id: "claude-haiku-4-5",  label: "Claude Haiku 4.5",    tag: "Anthropic", desc: "极速响应，适合简单任务" },
  { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6",   tag: "Anthropic", desc: "质量/速度平衡，对话自然" },
  { id: "claude-opus-4-7",   label: "Claude Opus 4.7",     tag: "Anthropic", desc: "最强推理，适合深度长文" },
  { id: "qwen3-72b",         label: "Qwen3 72B",           tag: "阿里",     desc: "中文顶级，性价比极高" },
  { id: "qwen3-32b",         label: "Qwen3 32B",           tag: "阿里",     desc: "轻量均衡，日常够用" },
  { id: "gemini-2.5-pro",    label: "Gemini 2.5 Pro",      tag: "Google",   desc: "长上下文(1M)，适合超长文章" },
];

const durations = [
  { id: "free", label: "自由适应", desc: "根据文本长度自动决定" },
  { id: "short", label: "5-15 分钟", desc: "精悍短播" },
  { id: "long", label: "15-30 分钟", desc: "深度长谈" },
  { id: "extra_long", label: "30-60 分钟", desc: "专题长谈" },
  { id: "ultra_long", label: "60 分钟以上", desc: "超长对谈" },
];

export default function SettingsPage() {
  const selectedModel = useAppStore((s) => s.selectedModel);
  const selectedDuration = useAppStore((s) => s.selectedDuration);
  const highQuality = useAppStore((s) => s.highQuality);
  const bgMusic = useAppStore((s) => s.bgMusic);
  const setSelectedModel = useAppStore((s) => s.setSelectedModel);
  const setSelectedDuration = useAppStore((s) => s.setSelectedDuration);
  const setHighQuality = useAppStore((s) => s.setHighQuality);
  const setBgMusic = useAppStore((s) => s.setBgMusic);
  const setPage = useAppStore((s) => s.setPage);

  return (
    <div className="p-10 max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white">设置</h1>
            <p className="text-sm text-slate-500 mt-1">管理你的播客生成偏好</p>
          </div>
        </div>
        <button
          onClick={() => setPage("usage")}
          className="flex items-center gap-2 text-xs text-slate-400 hover:text-white bg-[#161618] border border-[#2a2a2a] rounded-lg px-3 py-2 transition-colors"
        >
          <BarChart3 size={14} />
          API 用量
        </button>
      </div>

      {/* Model Selection */}
      <div className="mb-8">
        <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Bot size={16} className="text-brand-pink" />
          生成模型
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
          {models.map((m) => (
            <button
              key={m.id}
              onClick={() => setSelectedModel(m.id)}
              className={`bg-[#161618] border rounded-xl p-3 text-left hover:border-white/10 transition-all ${
                selectedModel === m.id
                  ? "border-brand-pink bg-brand-pink/5"
                  : "border-[#2a2a2a]"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <div className="text-xs text-slate-600 font-medium">{m.tag}</div>
                <div
                  className={`w-3.5 h-3.5 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                    selectedModel === m.id
                      ? "border-brand-pink"
                      : "border-slate-600"
                  }`}
                >
                  {selectedModel === m.id && (
                    <div className="w-1.5 h-1.5 rounded-full bg-brand-pink" />
                  )}
                </div>
              </div>
              <div className="text-sm font-semibold text-white mb-1">{m.label}</div>
              <p className="text-[11px] text-slate-500 leading-tight">{m.desc}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Duration */}
      <div className="mb-8">
        <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Clock size={16} className="text-brand-pink" />
          播客时长
        </h2>
        <div className="grid grid-cols-5 gap-3">
          {durations.map((d) => (
            <button
              key={d.id}
              onClick={() => setSelectedDuration(d.id)}
              className={`bg-[#161618] border rounded-xl p-3 text-center hover:border-white/10 transition-all ${
                selectedDuration === d.id
                  ? "border-brand-pink bg-brand-pink/5"
                  : "border-[#2a2a2a]"
              }`}
            >
              <div className="text-sm font-bold text-white mb-1">{d.label}</div>
              <div className="text-[10px] text-slate-500">{d.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Audio Quality */}
      <div className="mb-8">
        <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Volume2 size={16} className="text-brand-pink" />
          音质设置
        </h2>
        <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="text-sm font-medium text-white">高品质模式</div>
              <div className="text-xs text-slate-500 mt-0.5">
                启用音频增强引擎，提供更自然的情绪起伏与呼吸感
              </div>
            </div>
            <button
              onClick={() => setHighQuality(!highQuality)}
              className={`w-11 h-6 rounded-full relative cursor-pointer flex-shrink-0 transition-colors ${
                highQuality ? "bg-brand-pink" : "bg-white/10"
              }`}
            >
              <div
                className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all ${
                  highQuality ? "right-1" : "left-1"
                }`}
              />
            </button>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-white">背景音乐</div>
              <div className="text-xs text-slate-500 mt-0.5">
                在播客开头与结尾添加轻音乐过渡（旧版兼容）
              </div>
            </div>
            <button
              onClick={() => setBgMusic(!bgMusic)}
              className={`w-11 h-6 rounded-full relative cursor-pointer flex-shrink-0 transition-colors ${
                bgMusic ? "bg-brand-pink" : "bg-white/10"
              }`}
            >
              <div
                className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all ${
                  bgMusic ? "right-1" : "left-1"
                }`}
              />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
