import { useState, useEffect } from "react";
import { Bot, Clock, Volume2, User, AlertTriangle, Mic, Music, Type, Save } from "lucide-react";
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

const BGM_STYLES = [
  { id: "warm", label: "暖室", desc: "温暖大调和弦" },
  { id: "cool", label: "静夜", desc: "冷静小调氛围" },
  { id: "micro", label: "微光", desc: "现代电子感" },
  { id: "minimal", label: "留白", desc: "极简房间音" },
];

const OUTRO_MODES = [
  { id: "template", label: "固定结束语" },
  { id: "ai_summary", label: "AI 本期总结" },
  { id: "none", label: "无片尾" },
];

const SPEAKERS = [
  { id: "男声", label: "男声" },
  { id: "女声", label: "女声" },
  { id: "双声", label: "双声" },
];

export default function SettingsPage() {
  const selectedModel = useAppStore((s) => s.selectedModel);
  const selectedDuration = useAppStore((s) => s.selectedDuration);
  const highQuality = useAppStore((s) => s.highQuality);
  const bgMusic = useAppStore((s) => s.bgMusic);
  const userName = useAppStore((s) => s.userName);
  const genCount = useAppStore((s) => s.genCount);
  const podcastSettings = useAppStore((s) => s.podcastSettings);
  const setSelectedModel = useAppStore((s) => s.setSelectedModel);
  const setSelectedDuration = useAppStore((s) => s.setSelectedDuration);
  const setHighQuality = useAppStore((s) => s.setHighQuality);
  const setBgMusic = useAppStore((s) => s.setBgMusic);
  const setPodcastSettings = useAppStore((s) => s.setPodcastSettings);
  const showToast = useAppStore((s) => s.showToast);

  const [localSettings, setLocalSettings] = useState(() => ({
    intro: {
      enabled: true,
      template: "欢迎收听播刻。今天我们要聊的是——{topic}。",
      speaker: "男声",
      voice_id: null,
      transition_style: "warm",
      transition_duration: 3.0,
      transition_volume: 0.15,
    },
    outro: {
      enabled: true,
      mode: "template",
      template: "以上就是本期节目的全部内容。感谢收听播刻，我们下期再见。",
      speaker: "男声",
      voice_id: null,
    },
    body_bgm: {
      enabled: false,
      style: "minimal",
      volume: 0.08,
      custom_path: null,
    },
    ...(podcastSettings || {}),
  }));

  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (podcastSettings) {
      setLocalSettings((prev) => ({ ...prev, ...podcastSettings }));
    }
  }, [podcastSettings]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const resp = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(localSettings),
      });
      const data = await resp.json();
      setPodcastSettings(data);
      showToast("播客品牌设置已保存", "success");
    } catch (e) {
      showToast("保存失败", "error");
    } finally {
      setSaving(false);
    }
  };

  const updateIntro = (key, value) =>
    setLocalSettings((prev) => ({
      ...prev,
      intro: { ...prev.intro, [key]: value },
    }));

  const updateOutro = (key, value) =>
    setLocalSettings((prev) => ({
      ...prev,
      outro: { ...prev.outro, [key]: value },
    }));

  const updateBodyBgm = (key, value) =>
    setLocalSettings((prev) => ({
      ...prev,
      body_bgm: { ...prev.body_bgm, [key]: value },
    }));

  return (
    <div className="p-10 max-w-2xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">设置</h1>
        <p className="text-sm text-slate-500 mt-1">管理你的播客生成偏好与品牌资产</p>
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

      {/* Podcast Brand / Audio Arrangement */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <Music size={16} className="text-brand-pink" />
            播客品牌（开场白与片尾）
          </h2>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-pink/10 hover:bg-brand-pink/20 text-brand-pink rounded-lg text-xs font-medium transition-all disabled:opacity-50"
          >
            <Save size={12} />
            {saving ? "保存中..." : "保存到服务端"}
          </button>
        </div>

        <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5 space-y-6">
          {/* Intro */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Mic size={14} className="text-brand-tertiary" />
                <span className="text-sm font-medium text-white">开场白</span>
              </div>
              <button
                onClick={() => updateIntro("enabled", !localSettings.intro.enabled)}
                className={`w-9 h-5 rounded-full relative cursor-pointer flex-shrink-0 transition-colors ${
                  localSettings.intro.enabled ? "bg-brand-pink" : "bg-white/10"
                }`}
              >
                <div
                  className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${
                    localSettings.intro.enabled ? "right-0.5" : "left-0.5"
                  }`}
                />
              </button>
            </div>

            {localSettings.intro.enabled && (
              <div className="space-y-3 pl-6 border-l border-[#2a2a2a]">
                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">开场白文案（支持 {"{topic}"} 占位符）</label>
                  <textarea
                    value={localSettings.intro.template}
                    onChange={(e) => updateIntro("template", e.target.value)}
                    rows={2}
                    className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg p-2.5 text-xs text-white placeholder-slate-600 resize-none outline-none focus:border-brand-pink/30"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[10px] text-slate-500 mb-1 block">说话人</label>
                    <div className="flex gap-2">
                      {SPEAKERS.map((s) => (
                        <button
                          key={s.id}
                          onClick={() => updateIntro("speaker", s.id)}
                          className={`flex-1 py-1.5 rounded-lg text-xs transition-all ${
                            localSettings.intro.speaker === s.id
                              ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                              : "bg-white/5 text-slate-400 border border-transparent hover:bg-white/10"
                          }`}
                        >
                          {s.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 mb-1 block">过渡音乐风格</label>
                    <select
                      value={localSettings.intro.transition_style}
                      onChange={(e) => updateIntro("transition_style", e.target.value)}
                      className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg py-1.5 px-2 text-xs text-white outline-none focus:border-brand-pink/30"
                    >
                      {BGM_STYLES.map((s) => (
                        <option key={s.id} value={s.id}>{s.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[10px] text-slate-500 mb-1 block">过渡时长: {localSettings.intro.transition_duration.toFixed(1)}s</label>
                    <input
                      type="range"
                      min={1}
                      max={8}
                      step={0.5}
                      value={localSettings.intro.transition_duration}
                      onChange={(e) => updateIntro("transition_duration", parseFloat(e.target.value))}
                      className="w-full accent-brand-pink"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 mb-1 block">过渡音量: {Math.round(localSettings.intro.transition_volume * 100)}%</label>
                    <input
                      type="range"
                      min={0.05}
                      max={0.3}
                      step={0.01}
                      value={localSettings.intro.transition_volume}
                      onChange={(e) => updateIntro("transition_volume", parseFloat(e.target.value))}
                      className="w-full accent-brand-pink"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Outro */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Type size={14} className="text-brand-tertiary" />
                <span className="text-sm font-medium text-white">片尾</span>
              </div>
              <button
                onClick={() => updateOutro("enabled", !localSettings.outro.enabled)}
                className={`w-9 h-5 rounded-full relative cursor-pointer flex-shrink-0 transition-colors ${
                  localSettings.outro.enabled ? "bg-brand-pink" : "bg-white/10"
                }`}
              >
                <div
                  className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${
                    localSettings.outro.enabled ? "right-0.5" : "left-0.5"
                  }`}
                />
              </button>
            </div>

            {localSettings.outro.enabled && (
              <div className="space-y-3 pl-6 border-l border-[#2a2a2a]">
                <div className="flex gap-2">
                  {OUTRO_MODES.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => updateOutro("mode", m.id)}
                      className={`flex-1 py-1.5 rounded-lg text-xs transition-all ${
                        localSettings.outro.mode === m.id
                          ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                          : "bg-white/5 text-slate-400 border border-transparent hover:bg-white/10"
                      }`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>

                {localSettings.outro.mode === "template" && (
                  <div>
                    <label className="text-[10px] text-slate-500 mb-1 block">片尾结束语</label>
                    <textarea
                      value={localSettings.outro.template}
                      onChange={(e) => updateOutro("template", e.target.value)}
                      rows={2}
                      className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg p-2.5 text-xs text-white placeholder-slate-600 resize-none outline-none focus:border-brand-pink/30"
                    />
                  </div>
                )}

                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">说话人</label>
                  <div className="flex gap-2">
                    {SPEAKERS.slice(0, 2).map((s) => (
                      <button
                        key={s.id}
                        onClick={() => updateOutro("speaker", s.id)}
                        className={`flex-1 py-1.5 rounded-lg text-xs transition-all ${
                          localSettings.outro.speaker === s.id
                            ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                            : "bg-white/5 text-slate-400 border border-transparent hover:bg-white/10"
                        }`}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Body BGM default */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Music size={14} className="text-brand-tertiary" />
                <span className="text-sm font-medium text-white">正文背景音乐（默认）</span>
              </div>
              <button
                onClick={() => updateBodyBgm("enabled", !localSettings.body_bgm.enabled)}
                className={`w-9 h-5 rounded-full relative cursor-pointer flex-shrink-0 transition-colors ${
                  localSettings.body_bgm.enabled ? "bg-brand-pink" : "bg-white/10"
                }`}
              >
                <div
                  className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${
                    localSettings.body_bgm.enabled ? "right-0.5" : "left-0.5"
                  }`}
                />
              </button>
            </div>

            {localSettings.body_bgm.enabled && (
              <div className="pl-6 border-l border-[#2a2a2a] space-y-3">
                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">默认风格</label>
                  <select
                    value={localSettings.body_bgm.style}
                    onChange={(e) => updateBodyBgm("style", e.target.value)}
                    className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg py-1.5 px-2 text-xs text-white outline-none focus:border-brand-pink/30"
                  >
                    {BGM_STYLES.map((s) => (
                      <option key={s.id} value={s.id}>{s.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">默认音量: {Math.round(localSettings.body_bgm.volume * 100)}%</label>
                  <input
                    type="range"
                    min={0.02}
                    max={0.2}
                    step={0.01}
                    value={localSettings.body_bgm.volume}
                    onChange={(e) => updateBodyBgm("volume", parseFloat(e.target.value))}
                    className="w-full accent-brand-pink"
                  />
                </div>
              </div>
            )}
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
