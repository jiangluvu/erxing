import { useState, useEffect } from "react";
import { Heart, Play, Trash2 } from "lucide-react";
import { useAppStore } from "../store";
import { getFavorites, deleteFavorite } from "../api";

function formatRelativeTime(ts) {
  if (!ts) return "刚刚";
  const diff = Date.now() / 1000 - new Date(ts).getTime() / 1000;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`;
  return `${Math.floor(diff / 604800)} 周前`;
}

export default function FavoritesPage() {
  const [favorites, setFavorites] = useState([]);
  const [loading, setLoading] = useState(true);
  const setPage = useAppStore((s) => s.setPage);

  useEffect(() => {
    getFavorites()
      .then((data) => {
        setFavorites(data?.favorites || []);
      })
      .catch(() => setFavorites([]))
      .finally(() => setLoading(false));
  }, []);

  const handleDelete = async (id) => {
    try {
      await deleteFavorite(id);
      setFavorites((prev) => prev.filter((f) => f.id !== id));
    } catch {
      setFavorites((prev) => prev.filter((f) => f.id !== id));
    }
  };

  return (
    <div className="p-10 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-2">收藏</h1>
      <p className="text-sm text-slate-500 mb-6">你收藏的播客</p>

      {loading ? (
        <div className="text-center py-12 text-sm text-slate-500">加载中…</div>
      ) : favorites.length > 0 ? (
        <div className="space-y-3">
          {favorites.map((fav) => (
            <div
              key={fav.id}
              className="flex items-center gap-4 bg-[#161618] border border-[#2a2a2a] rounded-2xl p-4 hover:border-white/10 transition-all cursor-pointer group"
              onClick={() => setPage("player")}
            >
              <div className="w-10 h-10 rounded-xl bg-brand-pink/10 flex items-center justify-center flex-shrink-0">
                <Heart size={18} className="text-brand-pink" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-semibold text-white truncate">
                  {fav.session_id}
                </h3>
                <p className="text-xs text-slate-500">
                  {formatRelativeTime(fav.created_at)}
                </p>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <button className="p-2 rounded-lg hover:bg-white/5 text-slate-500 hover:text-white transition-all">
                  <Play size={16} />
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(fav.id);
                  }}
                  className="p-2 rounded-lg hover:bg-white/5 text-slate-500 hover:text-red-400 transition-all opacity-0 group-hover:opacity-100"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
            <Heart size={28} className="text-slate-600" />
          </div>
          <h3 className="text-white font-semibold mb-1">还没有收藏</h3>
          <p className="text-sm text-slate-500 mb-6">
            在播放器中点击收藏按钮，把喜欢的播客保存到这里
          </p>
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
