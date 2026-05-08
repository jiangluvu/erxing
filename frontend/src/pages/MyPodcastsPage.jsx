import { useState, useEffect } from "react";
import { Play, AlertCircle, RefreshCw } from "lucide-react";
import { useAppStore } from "../store";
import { getPodcasts } from "../api";

function SkeletonCard() {
  return (
    <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl overflow-hidden animate-pulse">
      <div className="h-36 bg-white/5"></div>
      <div className="p-4 space-y-3">
        <div className="h-4 bg-white/5 rounded w-3/4"></div>
        <div className="h-3 bg-white/5 rounded w-1/2"></div>
        <div className="flex justify-between">
          <div className="h-3 bg-white/5 rounded w-16"></div>
          <div className="h-3 bg-white/5 rounded w-12"></div>
        </div>
      </div>
    </div>
  );
}

function formatRelativeTime(ts) {
  if (!ts) return "刚刚";
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`;
  if (diff < 2592000) return `${Math.floor(diff / 604800)} 周前`;
  return `${Math.floor(diff / 2592000)} 个月前`;
}

function durationLabel(d) {
  const map = { short: "5 分钟", standard: "10 分钟", long: "15 分钟" };
  return map[d] || "10 分钟";
}

const gradients = [
  "from-brand-pink/20 to-brand-tertiary/20",
  "from-brand-tertiary/20 to-[#5E9EFF]/20",
  "from-[#5E9EFF]/20 to-brand-pink/20",
];

export default function MyPodcastsPage() {
  const [podcasts, setPodcasts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const setPage = useAppStore((s) => s.setPage);
  const setCurrentPodcast = useAppStore((s) => s.setCurrentPodcast);
  const setSessionId = useAppStore((s) => s.setSessionId);
  const showToast = useAppStore((s) => s.showToast);

  const handleClick = (podcast) => {
    setSessionId(podcast.id);
    setCurrentPodcast({
      title: podcast.title || podcast.article_title,
      platform: podcast.platform || "网页",
      time: formatRelativeTime(podcast.created_at),
      sessionId: podcast.id,
    });
    setPage("player");
  };

  const load = () => {
    setLoading(true);
    setError(null);
    getPodcasts()
      .then((data) => {
        setPodcasts(data?.podcasts || []);
      })
      .catch((e) => {
        setError(e.message || "加载失败");
        setPodcasts([]);
        showToast(e.message || "加载失败", "error");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="p-10 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">我的播客</h1>
        <p className="text-sm text-slate-500 mt-1">你生成的所有播客</p>
      </div>

      {loading ? (
        <div className="grid grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
            <AlertCircle size={28} className="text-slate-600" />
          </div>
          <h3 className="text-white font-semibold mb-1">加载失败</h3>
          <p className="text-sm text-slate-500 mb-6">{error}</p>
          <button
            onClick={load}
            className="px-4 py-2.5 bg-white text-black rounded-xl text-sm font-bold hover:bg-white/90 transition-all flex items-center gap-2"
          >
            <RefreshCw size={16} />
            重试
          </button>
        </div>
      ) : podcasts.length > 0 ? (
        <div className="grid grid-cols-3 gap-4">
          {podcasts.map((podcast, i) => (
            <div
              key={podcast.id}
              className="bg-[#161618] border border-[#2a2a2a] rounded-2xl overflow-hidden hover:border-white/10 transition-all cursor-pointer group"
              onClick={() => handleClick(podcast)}
            >
              <div
                className={`h-36 bg-gradient-to-br ${
                  gradients[i % gradients.length]
                } flex items-center justify-center relative`}
              >
                <span className="text-3xl">🎙️</span>
                <div className="absolute top-3 right-3 px-2 py-0.5 rounded bg-black/50 text-[10px] text-white backdrop-blur-sm">
                  {durationLabel(podcast.duration)}
                </div>
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/20">
                  <div className="w-12 h-12 rounded-full bg-white/90 flex items-center justify-center text-black">
                    <Play size={20} className="ml-0.5" />
                  </div>
                </div>
              </div>
              <div className="p-4">
                <h3 className="text-sm font-semibold text-white mb-1 line-clamp-1">
                  {podcast.title || podcast.article_title || "未命名播客"}
                </h3>
                <p className="text-xs text-slate-500 mb-3 line-clamp-2">
                  {podcast.platform || "网页"} · {durationLabel(podcast.duration)}
                </p>
                <div className="flex items-center justify-between">
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded border ${
                      podcast.status === "complete"
                        ? "bg-brand-pink/10 text-brand-pink border-brand-pink/20"
                        : "bg-red-500/10 text-red-400 border-red-500/20"
                    }`}
                  >
                    {podcast.status === "complete" ? "已就绪" : "生成失败"}
                  </span>
                  <span className="text-xs text-slate-500">
                    {formatRelativeTime(podcast.created_at)}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
            <Play size={28} className="text-slate-600" />
          </div>
          <h3 className="text-white font-semibold mb-1">还没有播客</h3>
          <p className="text-sm text-slate-500 mb-6">去首页生成你的第一个播客吧</p>
          <button
            onClick={() => setPage("home")}
            className="px-4 py-2.5 bg-white text-black rounded-xl text-sm font-bold hover:bg-white/90 transition-all"
          >
            去生成
          </button>
        </div>
      )}
    </div>
  );
}
