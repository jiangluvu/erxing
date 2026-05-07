import { useState } from "react";
import {
  Sparkles,
  SlidersHorizontal,
  Bot,
  Users,
  AudioLines,
  Loader2,
} from "lucide-react";
import { useAppStore } from "../store";
import { useGeneration } from "../hooks/useGeneration";

const tabs = ["链接", "文本", "上传", "探索"];

const placeholders = {
  链接: "粘贴文章链接，支持批量输入...",
  文本: "粘贴或输入文章内容...",
  上传: "拖拽文件到此处，或点击上传...",
  探索: "搜索感兴趣的主题或关键词...",
};

export default function ZeroStatePage() {
  const [activeTab, setActiveTab] = useState("链接");
  const [inputValue, setInputValue] = useState("");

  const generationStatus = useAppStore((s) => s.generationStatus);
  const generationProgress = useAppStore((s) => s.generationProgress);
  const statusText = useAppStore((s) => s.statusText);
  const setPage = useAppStore((s) => s.setPage);
  const { startGeneration } = useGeneration();

  const handleGenerate = async () => {
    const trimmed = inputValue.trim();
    if (!trimmed || trimmed.length < 5) {
      alert("请输入链接或文本");
      return;
    }
    const isUrl = trimmed.startsWith("http://") || trimmed.startsWith("https://");
    const payload = isUrl ? { url: trimmed } : { text: trimmed };

    try {
      await startGeneration(payload);
      setPage("generation");
    } catch (e) {
      alert(e.message || "生成失败");
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
              支持 AI 双人对话播客
            </span>
            <span className="h-1 w-1 rounded-full bg-brand-pink" />
            <span className="text-[10px] font-black text-brand-pink">NEW</span>
          </div>
          <h1 className="text-white font-bold tracking-tight text-3xl">
            耳行 让每一篇文章，变成一场对谈
          </h1>
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
              <button className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors">
                <SlidersHorizontal size={16} />
                <span>生成设置</span>
              </button>
              <button className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors">
                <Bot size={16} />
                <span>默认模型</span>
              </button>
            </div>
            <button className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
              快速粘贴
            </button>
          </div>
        </div>

        {/* Quick Experience */}
        <div className="flex items-center justify-center gap-3">
          <span className="text-xs text-slate-600">快速体验：</span>
          <a
            className="px-3 py-1.5 bg-[#1a1a1c] border border-white/5 rounded-full text-xs text-slate-400 hover:text-white transition-all"
            href="#"
            onClick={(e) => {
              e.preventDefault();
              setInputValue("科技周刊：AI 时代的数字生活");
            }}
          >
            科技周刊：AI 时代的数字生活
          </a>
          <a
            className="px-3 py-1.5 bg-[#1a1a1c] border border-white/5 rounded-full text-xs text-slate-400 hover:text-white transition-all"
            href="#"
            onClick={(e) => {
              e.preventDefault();
              setInputValue("深度：播客如何重塑我们的听觉");
            }}
          >
            深度：播客如何重塑我们的听觉
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
                : "一键生成"}
            </span>
          </button>
          <div className="flex items-center gap-8">
            <a
              className="text-xs text-slate-500 hover:text-brand-pink transition-colors underline underline-offset-4"
              href="#"
            >
              热门内容
            </a>
            <a
              className="text-xs text-slate-500 hover:text-brand-pink transition-colors underline underline-offset-4"
              href="#"
            >
              批量生成
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
              拟人化双人对谈
            </h4>
            <p className="text-xs text-slate-500 leading-relaxed">
              AI
              自动识别文章核心观点，模拟主持人与嘉宾的多维度深度对谈，告别单一朗读。
            </p>
          </div>
          <div className="p-6 rounded-2xl bg-white/5 border border-white/5 flex flex-col gap-3">
            <div className="h-10 w-10 rounded-xl bg-brand-tertiary/10 flex items-center justify-center">
              <AudioLines size={20} className="text-brand-tertiary" />
            </div>
            <h4 className="text-white font-semibold text-sm">
              高品质音色还原
            </h4>
            <p className="text-xs text-slate-500 leading-relaxed">
              自研音频增强引擎，提供自然的情绪起伏与呼吸感，带来身临其境的听觉体验。
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
