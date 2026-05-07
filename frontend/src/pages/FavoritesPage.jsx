import { Heart, Play, Trash2 } from "lucide-react";
import { useAppStore } from "../store";

const mockFavorites = [
  {
    id: "1",
    title: "AI 时代的数字生活变革",
    meta: "公众号 · 12 分钟 · 3 天前",
  },
  {
    id: "2",
    title: "DeepSeek 崛起：中国 AI 的新格局",
    meta: "知乎 · 15 分钟 · 1 周前",
  },
];

export default function FavoritesPage() {
  const setPage = useAppStore((s) => s.setPage);

  return (
    <div className="p-10 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-2">收藏</h1>
      <p className="text-sm text-slate-500 mb-6">你收藏的播客</p>

      {mockFavorites.length > 0 ? (
        <div className="space-y-3">
          {mockFavorites.map((fav) => (
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
                  {fav.title}
                </h3>
                <p className="text-xs text-slate-500">{fav.meta}</p>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <button className="p-2 rounded-lg hover:bg-white/5 text-slate-500 hover:text-white transition-all">
                  <Play size={16} />
                </button>
                <button className="p-2 rounded-lg hover:bg-white/5 text-slate-500 hover:text-red-400 transition-all opacity-0 group-hover:opacity-100">
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Empty State */
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
