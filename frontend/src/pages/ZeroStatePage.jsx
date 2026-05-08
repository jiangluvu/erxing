import { useState } from "react";
import {
  Sparkles,
  SlidersHorizontal,
  Bot,
  Users,
  AudioLines,
  Loader2,
  Zap,
} from "lucide-react";
import { useAppStore } from "../store";
import { useGeneration } from "../hooks/useGeneration";

const tabs = ["链接", "文本", "上传", "探索"];

const placeholders = {
  链接: "粘贴公众号/知乎文章链接，一键生成播客...",
  文本: "粘贴或输入文章正文...",
  上传: "拖拽文章文件到此处，或点击上传...",
  探索: "搜索感兴趣的话题或关键词...",
};

export default function ZeroStatePage() {
  const [activeTab, setActiveTab] = useState("链接");
  const [inputValue, setInputValue] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const [showModel, setShowModel] = useState(false);

  const generationStatus = useAppStore((s) => s.generationStatus);
  const generationProgress = useAppStore((s) => s.generationProgress);
  const statusText = useAppStore((s) => s.statusText);
  const setPage = useAppStore((s) => s.setPage);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const setSelectedModel = useAppStore((s) => s.setSelectedModel);
  const selectedDuration = useAppStore((s) => s.selectedDuration);
  const setSelectedDuration = useAppStore((s) => s.setSelectedDuration);
  const highQuality = useAppStore((s) => s.highQuality);
  const setHighQuality = useAppStore((s) => s.setHighQuality);
  const bgMusic = useAppStore((s) => s.bgMusic);
  const setBgMusic = useAppStore((s) => s.setBgMusic);
  const showToast = useAppStore((s) => s.showToast);
  const { startGeneration } = useGeneration();

  const handleGenerate = async () => {
    const trimmed = inputValue.trim();
    if (!trimmed || trimmed.length < 5) {
      showToast("请输入链接或文本", "error");
      return;
    }
    const isUrl = trimmed.startsWith("http://") || trimmed.startsWith("https://");
    const payload = {
      ...(isUrl ? { url: trimmed } : { text: trimmed }),
      model: selectedModel,
      duration: selectedDuration,
      high_quality: highQuality,
      bg_music: bgMusic,
    };

    try {
      await startGeneration(payload);
      setPage("generation");
    } catch (e) {
      showToast(e.message || "生成失败", "error");
    }
  };

  return (
    <div className="relative overflow-hidden flex flex-col items-center justify-center min-h-screen p-10">
      {/* Background glows */}
      <div className="absolute top-[-10%] right-[-5%] w-[600px] h-[600px] bg-brand-pink/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] left-[-5%] w-[400px] h-[400px] bg-[#a9c7ff]/5 rounded-full blur-[100px] pointer-events-none" />

      <div className="max-w-2xl w-full space-y-6 relative z-10">
        {/* Header */}
        <div className="text-center space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10 backdrop-blur-sm">
            <span className="text-[11px] font-bold text-slate-400 tracking-wider">
              知识创作者的 AI 播客引擎
            </span>
            <span className="h-1 w-1 rounded-full bg-brand-pink" />
            <span className="text-[10px] font-black text-brand-pink">NEW</span>
          </div>
          <h1 className="text-white font-bold tracking-tight text-3xl">
            你的文章，值得被听见
          </h1>
          <p className="text-sm text-slate-500">
            4 小时制作 → 5 分钟完成。把深度文章自动变成双人对话播客，直接上架小宇宙。
          </p>
        </div>

        {/* Input Card */}
        <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl overflow-hidden accent-glow transition-all duration-300">
          {/* Tabs */}
          <div className="flex border-b border-[#2a2a2a] bg-[#1a1a1c]">
            {tabs.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-6 py-4 text-sm font-medium transition-all ${
                  activeTab === tab
                    ? "text-brand-pink border-b-2 border-brand-pink bg-brand-pink/5"
                    : "text-slate-500 hover:text-slate-300"
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Input Area */}
          <div className="p-6">
            <textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              className="w-full h-32 bg-transparent border-none focus:ring-0 text-white placeholder-slate-600 resize-none text-sm outline-none"
              placeholder={placeholders[activeTab]}
            />
          </div>

          {/* Footer Actions */}
          <div className="px-6 py-4 border-t border-[#2a2a2a] flex items-center justify-between">
            <div className="flex gap-4">
              <button
                onClick={() => setShowSettings((v) => !v)}
                className={`flex items-center gap-1.5 text-xs transition-colors ${
                  showSettings ? "text-brand-pink" : "text-slate-500 hover:text-slate-300"
                }`}
              >
                <SlidersHorizontal size={16} />
                <span>生成设置</span>
              </button>
              <button
                onClick={() => setShowModel((v) => !v)}
                className={`flex items-center gap-1.5 text-xs transition-colors ${
                  showModel ? "text-brand-pink" : "text-slate-500 hover:text-slate-300"
                }`}
              >
                <Bot size={16} />
                <span>默认模型</span>
              </button>
            </div>
            <button className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
              快速粘贴
            </button>
          </div>

          {/* Settings Panel */}
          {showSettings && (
            <div className="px-6 pb-4 border-t border-[#2a2a2a] bg-[#1a1a1c]">
              <div className="pt-4 space-y-4">
                <div>
                  <span className="text-xs text-slate-500 mb-2 block">时长</span>
                  <div className="flex gap-2">
                    {[
                      { value: "short", label: "5 分钟" },
                      { value: "standard", label: "10 分钟" },
                      { value: "long", label: "15 分钟" },
                    ].map((opt) => (
                      <button
                        key={opt.value}
                        onClick={() => setSelectedDuration(opt.value)}
                        className={`px-3 py-1.5 rounded-lg text-xs border transition-all ${
                          selectedDuration === opt.value
                            ? "bg-brand-pink/10 text-brand-pink border-brand-pink/20"
                            : "bg-white/5 text-slate-400 border-white/5 hover:text-white"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={highQuality}
                      onChange={(e) => setHighQuality(e.target.checked)}
                      className="accent-brand-pink"
                    />
                    <span className="text-xs text-slate-400">高品质音频</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={bgMusic}
                      onChange={(e) => setBgMusic(e.target.checked)}
                      className="accent-brand-pink"
                    />
                    <span className="text-xs text-slate-400">背景音乐</span>
                  </label>
                </div>
              </div>
            </div>
          )}

          {/* Model Panel */}
          {showModel && (
            <div className="px-6 pb-4 border-t border-[#2a2a2a] bg-[#1a1a1c]">
              <div className="pt-4">
                <span className="text-xs text-slate-500 mb-2 block">模型</span>
                <div className="flex gap-2">
                  {[
                    { value: "kimi", label: "Kimi" },
                    { value: "deepseek", label: "DeepSeek" },
                    { value: "gpt4o", label: "GPT-4o" },
                  ].map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setSelectedModel(opt.value)}
                      className={`px-3 py-1.5 rounded-lg text-xs border transition-all ${
                        selectedModel === opt.value
                          ? "bg-brand-pink/10 text-brand-pink border-brand-pink/20"
                          : "bg-white/5 text-slate-400 border-white/5 hover:text-white"
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Quick Experience */}
        <div className="flex items-center justify-center gap-3">
          <span className="text-xs text-slate-600">快速体验：</span>
          <a
            className="px-3 py-1.5 bg-[#1a1a1c] border border-white/5 rounded-full text-xs text-slate-400 hover:text-white transition-all"
            href="#"
            onClick={(e) => {
              e.preventDefault();
              setInputValue("AI 时代的教育变革：为什么我们需要重新定义学习");
            }}
          >
            科技长文 → 播客
          </a>
          <a
            className="px-3 py-1.5 bg-[#1a1a1c] border border-white/5 rounded-full text-xs text-slate-400 hover:text-white transition-all"
            href="#"
            onClick={(e) => {
              e.preventDefault();
              setInputValue("2026 年新能源汽车市场趋势：价格战后的新格局");
            }}
          >
            商业分析 → 播客
          </a>
        </div>

        {/* Primary CTA */}
        <div className="flex flex-col items-center gap-6 pt-3">
          <button
            onClick={handleGenerate}
            disabled={generationStatus === "generating"}
            className="group relative flex items-center gap-3 px-12 py-4 bg-white hover:bg-white/90 disabled:bg-white/60 text-black rounded-full font-bold text-lg transition-all active:scale-95 shadow-[0_0_40px_rgba(255,255,255,0.1)] disabled:cursor-not-allowed"
          >
            {generationStatus === "generating" ? (
              <Loader2 size={20} className="animate-spin" />
            ) : (
              <Sparkles size={20} />
            )}
            <span>
              {generationStatus === "generating"
                ? `${statusText} (${generationProgress}%)`
                : "开始制作播客"}
            </span>
          </button>
          <div className="flex items-center gap-8">
            <a
              className="text-xs text-slate-500 hover:text-brand-pink transition-colors underline underline-offset-4"
              href="#"
              onClick={(e) => {
                e.preventDefault();
                setPage("hot");
              }}
            >
              创作灵感
            </a>
            <a
              className="text-xs text-slate-500 hover:text-brand-pink transition-colors underline underline-offset-4"
              href="#"
              onClick={(e) => {
                e.preventDefault();
                setPage("myPodcasts");
              }}
            >
              我的内容
            </a>
          </div>
        </div>

        {/* Feature Showcase Bento */}
        <div className="grid grid-cols-2 gap-4 mt-10">
          <div className="p-6 rounded-2xl bg-white/5 border border-white/5 flex flex-col gap-3">
            <div className="h-10 w-10 rounded-xl bg-brand-pink/10 flex items-center justify-center">
              <Users size={20} className="text-brand-pink" />
            </div>
            <h4 className="text-white font-semibold text-sm">
              AI 演绎文章观点
            </h4>
            <p className="text-xs text-slate-500 leading-relaxed">
              AI 自动提取文章核心论点，生成主持人与嘉宾的深度对谈。不是单调朗读，而是有论证、有例子的互动演绎，完播率远高于单人播报。
            </p>
          </div>
          <div className="p-6 rounded-2xl bg-white/5 border border-white/5 flex flex-col gap-3">
            <div className="h-10 w-10 rounded-xl bg-brand-tertiary/10 flex items-center justify-center">
              <Zap size={20} className="text-brand-tertiary" />
            </div>
            <h4 className="text-white font-semibold text-sm">
              分钟级内容生产
            </h4>
            <p className="text-xs text-slate-500 leading-relaxed">
              从文章链接到可发布播客只需 5 分钟。响度标准化 + 智能音频后处理，直接达到小宇宙、喜马拉雅发布标准，无需二次剪辑。
            </p>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="absolute bottom-10 text-center w-full">
        <p className="text-[10px] text-slate-700 tracking-widest uppercase">
          Earline v2.0.4 — The Luminescent Guide
        </p>
      </footer>
    </div>
  );
}
