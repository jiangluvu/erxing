import { useState } from "react";
import { useAppStore } from "../store";
import { addNote, downloadPodcast } from "../api";
import {
  ArrowLeft,
  Play,
  Heart,
  Download,
  Share2,
  ExternalLink,
  FileText,
  Clock,
  Bookmark,
} from "lucide-react";

const chapters = [
  {
    num: "01",
    title: "核心观点导入",
    desc: "主持和嘉宾介绍了今天的主题和文章背景",
    time: "00:00 - 02:30",
  },
  {
    num: "02",
    title: "深度分析",
    desc: "两位主持人从不同角度分析了文章的核心论点",
    time: "02:30 - 08:45",
  },
  {
    num: "03",
    title: "总结与思考",
    desc: "回顾关键 takeaways，延伸思考",
    time: "08:45 - 12:34",
  },
];

export default function DetailPage() {
  const setPage = useAppStore((s) => s.setPage);
  const currentPodcast = useAppStore((s) => s.currentPodcast);
  const scriptData = useAppStore((s) => s.scriptData);
  const sessionId = useAppStore((s) => s.sessionId);
  const [toast, setToast] = useState("");

  const title = currentPodcast?.title || "播客详情";
  const platform = currentPodcast?.platform || "网页";
  const time = currentPodcast?.time || "刚刚";

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 2000);
  };

  // Build a simple summary from script if available
  const summary =
    scriptData?.length > 0
      ? `${scriptData[0].speaker === "主持" ? "主持" : "嘉宾"}和${scriptData[1]?.speaker === "主持" ? "主持" : scriptData[1]?.speaker === "嘉宾" ? "嘉宾" : "嘉宾"}围绕文章的核心观点展开了深入讨论，从多个维度分析了文章的论点、背景与延伸思考。`
      : "主持和嘉宾围绕文章的核心观点展开了深入讨论…";

  const handleSaveNote = async () => {
    try {
      await addNote({
        session_id: sessionId || "detail_" + Date.now(),
        title: title || "播客笔记",
        content: summary,
      });
      showToast("已保存到笔记");
    } catch {
      showToast("保存失败");
    }
  };

  const handleDownload = async () => {
    if (!sessionId) {
      showToast("暂无可下载音频");
      return;
    }
    try {
      const blob = await downloadPodcast(sessionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${title || "podcast"}.mp3`;
      a.click();
      URL.revokeObjectURL(url);
      showToast("开始下载");
    } catch {
      showToast("下载失败");
    }
  };

  const handleShare = async () => {
    const text = title ? `${title} — 来自播刻播客` : "播刻播客";
    try {
      await navigator.clipboard.writeText(text);
      showToast("链接已复制到剪贴板");
    } catch {
      showToast("复制失败");
    }
  };

  const handleFavorite = () => {
    const favs = JSON.parse(localStorage.getItem("boke_favs") || "[]");
    const id = sessionId || currentPodcast?.id;
    if (!id) {
      showToast("暂无可收藏内容");
      return;
    }
    const idx = favs.indexOf(id);
    if (idx >= 0) {
      favs.splice(idx, 1);
      showToast("已取消收藏");
    } else {
      favs.push(id);
      showToast("已收藏");
    }
    localStorage.setItem("boke_favs", JSON.stringify(favs));
  };

  return (
    <div className="p-10 max-w-3xl mx-auto">
      {/* Breadcrumb */}
      <button
        onClick={() => setPage("myPodcasts")}
        className="flex items-center gap-2 text-xs text-slate-500 hover:text-white transition-colors mb-6"
      >
        <ArrowLeft size={14} />
        <span>返回</span>
      </button>

      {/* Title */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white mb-2">{title}</h1>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span className="flex items-center gap-1">
            <FileText size={12} />
            {platform}
          </span>
          <span>·</span>
          <span className="flex items-center gap-1">
            <Clock size={12} />
            {time}
          </span>
        </div>
      </div>

      {/* Source Card */}
      <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5 mb-6 flex items-center gap-4">
        <div className="w-10 h-10 rounded-xl bg-brand-pink/10 flex items-center justify-center">
          <FileText size={18} className="text-brand-pink" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-white truncate">
            来源文章
          </div>
          <div className="text-xs text-slate-500 truncate">
            {platform} · {time}
          </div>
        </div>
        <button className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-xs text-white transition-all">
          <ExternalLink size={14} />
          <span>访问原文</span>
        </button>
      </div>

      {/* Summary */}
      <div className="mb-6">
        <h2 className="text-sm font-semibold text-white mb-3">摘要</h2>
        <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
          <p className="text-sm text-slate-400 leading-relaxed">{summary}</p>
        </div>
      </div>

      {/* Chapters */}
      <div className="mb-8">
        <h2 className="text-sm font-semibold text-white mb-3">章节大纲</h2>
        <div className="space-y-3">
          {chapters.map((ch, i) => (
            <div
              key={ch.num}
              className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5 hover:border-white/10 transition-all cursor-pointer"
              onClick={() => setPage("player")}
            >
              <div className="flex items-start gap-4">
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                    i === 0
                      ? "bg-brand-pink/10 text-brand-pink"
                      : "bg-white/5 text-slate-500"
                  }`}
                >
                  {ch.num}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-semibold text-white">
                      {ch.title}
                    </span>
                    <span className="text-xs text-slate-500">{ch.time}</span>
                  </div>
                  <p className="text-xs text-slate-500">{ch.desc}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={() => setPage("player")}
          className="flex items-center gap-2 px-6 py-3 bg-white text-black rounded-xl text-sm font-bold hover:bg-white/90 transition-all"
        >
          <Play size={16} />
          <span>收听播客</span>
        </button>
        <button
          onClick={handleFavorite}
          className="flex items-center gap-2 px-4 py-3 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-all"
        >
          <Heart size={18} />
          <span className="text-sm">收藏</span>
        </button>
        <button
          onClick={handleSaveNote}
          className="flex items-center gap-2 px-4 py-3 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-all"
        >
          <Bookmark size={18} />
          <span className="text-sm">保存到笔记</span>
        </button>
        <button
          onClick={handleDownload}
          className="p-3 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-all"
        >
          <Download size={18} />
        </button>
        <button
          onClick={handleShare}
          className="p-3 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-all"
        >
          <Share2 size={18} />
        </button>
      </div>

      {toast && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 bg-[#1a1a1c] border border-[#2a2a2a] text-white text-sm px-5 py-2.5 rounded-xl shadow-lg z-50">
          {toast}
        </div>
      )}
    </div>
  );
}
