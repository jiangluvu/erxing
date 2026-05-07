import { useState, useEffect } from "react";
import { Clock, Headphones, Play, RotateCcw } from "lucide-react";
import { useAppStore } from "../store";
import { getHistory, deleteHistory } from "../api";

function formatDuration(s) {
  if (!s || isNaN(s)) return "00:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

function groupByDate(items) {
  const groups = {};
  items.forEach((item) => {
    const date = item.last_played_at
      ? new Date(item.last_played_at).toLocaleDateString("zh-CN")
      : "未知";
    const today = new Date().toLocaleDateString("zh-CN");
    const yesterday = new Date(Date.now() - 86400000).toLocaleDateString("zh-CN");
    let label = date;
    if (date === today) label = "今天";
    else if (date === yesterday) label = "昨天";
    if (!groups[label]) groups[label] = [];
    groups[label].push(item);
  });
  return groups;
}

export default function HistoryPage() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const setPage = useAppStore((s) => s.setPage);

  useEffect(() => {
    getHistory()
      .then((data) => {
        setHistory(data?.history || []);
      })
      .catch(() => setHistory([]))
      .finally(() => setLoading(false));
  }, []);

  const handleDelete = async (id) => {
    try {
      await deleteHistory(id);
      setHistory((prev) => prev.filter((h) => h.id !== id));
    } catch {
      setHistory((prev) => prev.filter((h) => h.id !== id));
    }
  };

  const groups = groupByDate(history);
  const groupOrder = ["今天", "昨天"].concat(
    Object.keys(groups).filter((k) => k !== "今天" && k !== "昨天")
  );

  return (
    <div className="p-10 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-2">历史记录</h1>
      <p className="text-sm text-slate-500 mb-6">你听过的播客</p>

      {loading ? (
        <div className="text-center py-12 text-sm text-slate-500">加载中…</div>
      ) : history.length > 0 ? (
        <div className="space-y-6">
          {groupOrder.map(
            (g) =>
              groups[g]?.length > 0 && (
                <div key={g}>
                  <div className="text-xs font-bold text-slate-600 uppercase tracking-widest mb-3">
                    {g}
                  </div>
                  <div className="space-y-2">
                    {groups[g].map((h) => {
                      const finished = h.progress >= h.duration;
                      return (
                        <div
                          key={h.id}
                          className="flex items-center gap-4 bg-[#161618] border border-[#2a2a2a] rounded-2xl p-4 hover:border-white/10 transition-all cursor-pointer"
                          onClick={() => setPage("player")}
                        >
                          <div className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center flex-shrink-0">
                            <Headphones
                              size={18}
                              className={finished ? "text-slate-500" : "text-brand-pink"}
                            />
                          </div>
                          <div className="flex-1 min-w-0">
                            <h3 className="text-sm font-semibold text-white truncate">
                              {h.session_id}
                            </h3>
                            <p className="text-xs text-slate-500">
                              {finished
                                ? "已听完"
                                : `播放到 ${formatDuration(h.progress)} / ${formatDuration(
                                    h.duration
                                  )}`}
                            </p>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <button className="p-2 rounded-lg hover:bg-white/5 text-slate-500 hover:text-white transition-all">
                              {finished ? (
                                <RotateCcw size={16} />
                              ) : (
                                <Play size={16} />
                              )}
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDelete(h.id);
                              }}
                              className="p-2 rounded-lg hover:bg-white/5 text-slate-500 hover:text-red-400 transition-all"
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
            <Clock size={28} className="text-slate-600" />
          </div>
          <h3 className="text-white font-semibold mb-1">还没有收听记录</h3>
          <p className="text-sm text-slate-500 mb-6">去首页生成你的第一个播客吧</p>
          <button
            onClick={() => setPage("home")}
            className="px-4 py-2.5 bg-white text-black rounded-xl text-sm font-bold"
          >
            去生成
          </button>
        </div>
      )}
    </div>
  );
}
