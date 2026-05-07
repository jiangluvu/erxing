import { Clock, Headphones, Play, RotateCcw } from "lucide-react";
import { useAppStore } from "../store";

const mockHistory = [
  {
    id: "1",
    title: "AI 时代的数字生活变革",
    meta: "播放到 8:32 / 12:34 · 公众号",
    time: "2 小时前",
    group: "今天",
    iconColor: "text-brand-pink",
    iconBg: "bg-brand-pink/10",
    finished: false,
  },
  {
    id: "2",
    title: "DeepSeek 崛起：中国 AI 的新格局",
    meta: "已听完 · 15 分钟 · 知乎",
    time: "昨天 21:40",
    group: "昨天",
    iconColor: "text-slate-500",
    iconBg: "bg-white/5",
    finished: true,
  },
  {
    id: "3",
    title: "SpaceX 星舰第五飞",
    meta: "播放到 5:10 / 10:20 · B站",
    time: "昨天 18:15",
    group: "昨天",
    iconColor: "text-slate-500",
    iconBg: "bg-white/5",
    finished: false,
  },
  {
    id: "4",
    title: "2026 年新能源汽车市场趋势",
    meta: "已听完 · 15 分钟 · 知乎",
    time: "5月2日",
    group: "更早",
    iconColor: "text-slate-500",
    iconBg: "bg-white/5",
    finished: true,
  },
];

const groups = ["今天", "昨天", "更早"];

export default function HistoryPage() {
  const setPage = useAppStore((s) => s.setPage);

  return (
    <div className="p-10 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-2">历史记录</h1>
      <p className="text-sm text-slate-500 mb-6">你听过的播客</p>

      {mockHistory.length > 0 ? (
        <div className="space-y-6">
          {groups.map(
            (g) =>
              mockHistory.some((h) => h.group === g) && (
                <div key={g}>
                  <div className="text-xs font-bold text-slate-600 uppercase tracking-widest mb-3">
                    {g}
                  </div>
                  <div className="space-y-2">
                    {mockHistory
                      .filter((h) => h.group === g)
                      .map((h) => (
                        <div
                          key={h.id}
                          className="flex items-center gap-4 bg-[#161618] border border-[#2a2a2a] rounded-2xl p-4 hover:border-white/10 transition-all cursor-pointer"
                          onClick={() => setPage("player")}
                        >
                          <div
                            className={`w-10 h-10 rounded-xl ${h.iconBg} flex items-center justify-center flex-shrink-0`}
                          >
                            <Headphones size={18} className={h.iconColor} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <h3 className="text-sm font-semibold text-white truncate">
                              {h.title}
                            </h3>
                            <p className="text-xs text-slate-500">{h.meta}</p>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <span className="text-xs text-slate-500">{h.time}</span>
                            <button className="p-2 rounded-lg hover:bg-white/5 text-slate-500 hover:text-white transition-all">
                              {h.finished ? <RotateCcw size={16} /> : <Play size={16} />}
                            </button>
                          </div>
                        </div>
                      ))}
                  </div>
                </div>
              )
          )}
        </div>
      ) : (
        /* Empty State */
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
