import { useState } from "react";
import { Flame, PlayCircle, Clock, Play } from "lucide-react";
import { useAppStore } from "../store";

const filters = ["全部", "科技", "商业", "文化", "生活方式"];

const mockHot = [
  {
    id: "1",
    title: "AI 时代的教育变革：为什么我们需要重新定义学习",
    tag: "精选",
    tagType: "featured",
    desc: "深度探讨了 AI 对教育体系的影响，从个性化学习到智能评估的全面变革…",
    plays: "2.3k",
    duration: "12 分钟",
    platform: "公众号",
  },
  {
    id: "2",
    title: "2026 年新能源汽车市场趋势：价格战后的新格局",
    tag: "热门",
    tagType: "hot",
    desc: "分析新能源汽车市场的竞争格局变化，从价格战到技术战的转型之路…",
    plays: "1.8k",
    duration: "15 分钟",
    platform: "知乎",
  },
  {
    id: "3",
    title: "特斯拉 FSD 入华：自动驾驶的新篇章",
    tag: "热门",
    tagType: "hot",
    desc: "FSD 正式进入中国，对本土企业产生的影响与竞争格局分析…",
    plays: "1.5k",
    duration: "10 分钟",
    platform: "B站",
  },
];

export default function HotPage() {
  const [activeFilter, setActiveFilter] = useState("全部");
  const setPage = useAppStore((s) => s.setPage);

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

      {/* Hot List */}
      <div className="space-y-3">
        {mockHot.map((item, i) => {
          const isFirst = i === 0;
          return (
            <div
              key={item.id}
              className="flex items-start gap-4 bg-[#161618] border border-[#2a2a2a] rounded-2xl p-4 hover:border-white/10 transition-all cursor-pointer"
              onClick={() => setPage("player")}
            >
              <div
                className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5 ${
                  isFirst ? "bg-brand-pink/10" : "bg-white/5"
                }`}
              >
                <span
                  className={`text-sm font-bold ${
                    isFirst ? "text-brand-pink" : "text-slate-400"
                  }`}
                >
                  {i + 1}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="text-sm font-semibold text-white">{item.title}</h3>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded border flex-shrink-0 ${
                      item.tagType === "featured"
                        ? "bg-brand-pink/10 text-brand-pink border-brand-pink/20"
                        : "bg-white/5 text-slate-500 border-white/5"
                    }`}
                  >
                    {item.tag}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mb-2">{item.desc}</p>
                <div className="flex items-center gap-3 text-xs text-slate-500">
                  <span className="flex items-center gap-1">
                    <PlayCircle size={12} /> {item.plays} 收听
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock size={12} /> {item.duration}
                  </span>
                  <span>{item.platform}</span>
                </div>
              </div>
              <button className="p-2 rounded-lg hover:bg-white/5 text-slate-500 hover:text-white transition-all flex-shrink-0">
                <Play size={16} />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
