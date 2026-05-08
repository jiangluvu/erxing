import { useState, useEffect } from "react";
import { Play, AlertCircle, RefreshCw } from "lucide-react";
import { useAppStore } from "../store";
import { getExplore } from "../api";

const filters = ["全部", "科技", "商业", "文化", "生活方式"];

function platformColor(platform) {
  const map = {
    公众号: "bg-brand-pink/10 text-brand-pink",
    知乎: "bg-[#5E9EFF]/10 text-[#5E9EFF]",
    B站: "bg-brand-tertiary/10 text-brand-tertiary",
    网页: "bg-white/5 text-slate-500",
    小红书: "bg-red-400/10 text-red-400",
  };
  return map[platform] || map["网页"];
}

function SkeletonRow() {
  return (
    <div className="flex items-start gap-4 bg-[#161618] border border-[#2a2a2a] rounded-2xl p-4 animate-pulse">
      <div className="w-10 h-10 rounded-xl bg-white/5 flex-shrink-0 mt-0.5"></div>
      <div className="flex-1 min-w-0 space-y-2">
        <div className="h-4 bg-white/5 rounded w-3/4"></div>
        <div className="h-3 bg-white/5 rounded w-1/2"></div>
        <div className="h-3 bg-white/5 rounded w-20"></div>
      </div>
      <div className="w-8 h-8 rounded-lg bg-white/5 flex-shrink-0"></div>
    </div>
  );
}

export default function HotPage() {
  const [activeFilter, setActiveFilter] = useState("全部");
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const setPage = useAppStore((s) => s.setPage);
  const setCurrentPodcast = useAppStore((s) => s.setCurrentPodcast);
  const setSessionId = useAppStore((s) => s.setSessionId);
  const setScriptData = useAppStore((s) => s.setScriptData);
  const setTimings = useAppStore((s) => s.setTimings);
  const setFullAudioUrl = useAppStore((s) => s.setFullAudioUrl);
  const setPreviewAudioUrl = useAppStore((s) => s.setPreviewAudioUrl);
  const showToast = useAppStore((s) => s.showToast);

  const load = () => {
    setLoading(true);
    setError(null);
    getExplore("all")
      .then((data) => {
        setArticles(data?.articles || []);
      })
      .catch((e) => {
        setError(e.message || "加载失败");
        setArticles([]);
        showToast(e.message || "加载失败", "error");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const filtered =
    activeFilter === "全部"
      ? articles
      : articles.filter((a) =>
          a.tag?.includes(activeFilter) || a.platform === activeFilter
        );

  return (
    <div className="p-10 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-2">热门内容</h1>
      <p className="text-sm text-slate-500 mb-6">本周最受欢迎的播客与文章</p>

      {/* Filter Pills */}
      <div className="flex items-center gap-2 mb-6 flex-wrap">
        {filters.map((f) => (
          <button
            key={f}
            onClick={() => setActiveFilter(f)}
            className={`px-3 py-1.5 border rounded-full text-xs font-medium transition-all ${
              activeFilter === f
                ? "bg-white/5 border-white/5 text-white"
                : "bg-transparent border-white/5 text-slate-500 hover:text-white"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonRow key={i} />
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
      ) : filtered.length > 0 ? (
        <div className="space-y-3">
          {filtered.map((item, i) => (
            <div
              key={item.id}
              className="flex items-start gap-4 bg-[#161618] border border-[#2a2a2a] rounded-2xl p-4 hover:border-white/10 transition-all cursor-pointer"
              onClick={() => {
                const previewScript = [
                  { speaker: "小姜", text: `今天咱们来聊聊《${item.title}》。` },
                  { speaker: "小羊", text: item.summary || item.desc },
                  ...(item.chapters || []).map((ch, i) => ({
                    speaker: i % 2 === 0 ? "小姜" : "小羊",
                    text: `${ch.t}，${ch.d}`,
                  })),
                ];
                const previewTimings = previewScript.map((_, i) => ({
                  start: i * 8,
                  end: (i + 1) * 8,
                }));
                setCurrentPodcast({
                  title: item.title,
                  platform: item.platform,
                  time: "刚刚",
                });
                setSessionId(item.id);
                setScriptData(previewScript);
                setTimings(previewTimings);
                setFullAudioUrl(null);
                setPreviewAudioUrl(null);
                setPage("player");
              }}
            >
              <div
                className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5 ${
                  i === 0 ? "bg-brand-pink/10" : "bg-white/5"
                }`}
              >
                <span
                  className={`text-sm font-bold ${
                    i === 0 ? "text-brand-pink" : "text-slate-400"
                  }`}
                >
                  {i + 1}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="text-sm font-semibold text-white">
                    {item.title}
                  </h3>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded border flex-shrink-0 ${
                      item.tag === "精选"
                        ? "bg-brand-pink/10 text-brand-pink border-brand-pink/20"
                        : "bg-white/5 text-slate-500 border-white/5"
                    }`}
                  >
                    {item.tag}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mb-2">{item.desc}</p>
                <div className="flex items-center gap-3 text-xs text-slate-500">
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-500 border border-white/5">
                    {item.platform}
                  </span>
                </div>
              </div>
              <button className="p-2 rounded-lg hover:bg-white/5 text-slate-500 hover:text-white transition-all flex-shrink-0">
                <Play size={16} />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-sm text-slate-500">
          该分类下暂无内容
        </div>
      )}
    </div>
  );
}
