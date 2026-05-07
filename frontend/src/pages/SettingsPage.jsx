import { Bot, Clock, Volume2, User, AlertTriangle } from "lucide-react";
import { useAppStore } from "../store";

const models = [
  { id: "kimi", label: "Kimi", desc: "均衡模式，适合大多数文章" },
  { id: "deepseek", label: "DeepSeek", desc: "深度推理，长文表现更佳" },
  { id: "gpt4o", label: "GPT-4o", desc: "创意丰富，对谈更生动" },
];

const durations = [
  { id: "short", label: "5 分钟", desc: "精悍短播" },
  { id: "standard", label: "10 分钟", desc: "标准深度" },
  { id: "long", label: "15 分钟", desc: "深度长谈" },
];

export default function SettingsPage() {
  const selectedModel = useAppStore((s) => s.selectedModel);
  const selectedDuration = useAppStore((s) => s.selectedDuration);
  const highQuality = useAppStore((s) => s.highQuality);
  const bgMusic = useAppStore((s) => s.bgMusic);
  const userName = useAppStore((s) => s.userName);
  const genCount = useAppStore((s) => s.genCount);
  const setSelectedModel = useAppStore((s) => s.setSelectedModel);
  const setSelectedDuration = useAppStore((s) => s.setSelectedDuration);
  const setHighQuality = useAppStore((s) => s.setHighQuality);
  const setBgMusic = useAppStore((s) => s.setBgMusic);

  return (
    <div className="p-10 max-w-2xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">设置</h1>
        <p className="text-sm text-slate-500 mt-1">管理你的播客生成偏好与账号信息</p>
      </div>

      {/* Model Selection */}
      <div className="mb-8">
        <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Bot size={16} className="text-brand-pink" />
          生成模型
        </h2>
        <div className="grid grid-cols-3 gap-3">
          {models.map((m) => (
            <button
              key={m.id}
              onClick={() => setSelectedModel(m.id)}
              className={`bg-[#161618] border rounded-xl p-4 text-left hover:border-white/10 transition-all ${
                selectedModel === m.id
                  ? "border-brand-pink bg-brand-pink/5"
                  : "border-[#2a2a2a]"
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-semibold text-white">{m.label}</div>
                <div
                  className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                    selectedModel === m.id
                      ? "border-brand-pink"
                      : "border-slate-600"
                  }`}
                >
                  {selectedModel === m.id && (
                    <div className="w-2 h-2 rounded-full bg-brand-pink" />
                  )}
                </div>
              </div>
              <p className="text-xs text-slate-500">{m.desc}</p>
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
        <div className="grid grid-cols-3 gap-3">
          {durations.map((d) => (
            <button
              key={d.id}
              onClick={() => setSelectedDuration(d.id)}
              className={`bg-[#161618] border rounded-xl p-4 text-center hover:border-white/10 transition-all ${
                selectedDuration === d.id
                  ? "border-brand-pink bg-brand-pink/5"
                  : "border-[#2a2a2a]"
              }`}
            >
              <div className="text-lg font-bold text-white mb-1">{d.label}</div>
              <div className="text-xs text-slate-500">{d.desc}</div>
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
                在播客开头与结尾添加轻音乐过渡
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

      {/* Account */}
      <div className="mb-8">
        <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <User size={16} className="text-brand-pink" />
          账号信息
        </h2>
        <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
          <div className="flex items-center gap-4 mb-5">
            <div className="w-12 h-12 rounded-full bg-brand-pink/10 flex items-center justify-center text-brand-pink font-bold text-lg">
              {userName[0]}
            </div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-white">{userName}</div>
              <div className="text-xs text-slate-500">免费用户 · 已生成 {genCount} 个播客</div>
            </div>
            <button className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-xs text-white transition-all border border-white/5">
              编辑资料
            </button>
          </div>
        </div>
      </div>

      {/* Danger Zone */}
      <div>
        <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <AlertTriangle size={16} className="text-red-400" />
          危险操作
        </h2>
        <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-white">清除所有数据</div>
              <div className="text-xs text-slate-500 mt-0.5">
                删除所有生成的播客、历史记录与设置
              </div>
            </div>
            <button className="px-3 py-1.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-xs text-red-400 transition-all border border-red-500/20">
              清除
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
