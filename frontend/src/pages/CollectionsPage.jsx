import { useState } from "react";
import { Plus, Folder, Headphones, MoreHorizontal } from "lucide-react";

const mockCollections = [
  {
    id: "1",
    name: "AI 专栏",
    count: 5,
    color: "text-brand-pink",
    bg: "bg-brand-pink/10",
    items: ["AI 时代的数字生活变革", "DeepSeek 崛起", "特斯拉 FSD 入华"],
  },
  {
    id: "2",
    name: "科技周报",
    count: 3,
    color: "text-brand-tertiary",
    bg: "bg-brand-tertiary/10",
    items: ["SpaceX 星舰第五飞", "2026 新能源汽车趋势"],
  },
];

export default function CollectionsPage() {
  const [collections, setCollections] = useState(mockCollections);

  const handleAdd = () => {
    const name = window.prompt("合集名称");
    if (!name?.trim()) return;
    setCollections((prev) => [
      ...prev,
      {
        id: String(Date.now()),
        name: name.trim(),
        count: 0,
        color: "text-brand-pink",
        bg: "bg-brand-pink/10",
        items: [],
      },
    ]);
  };

  return (
    <div className="p-10 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">我的合集</h1>
          <p className="text-sm text-slate-500 mt-1">整理你的播客，按主题归类</p>
        </div>
        <button
          onClick={handleAdd}
          className="flex items-center gap-2 px-4 py-2.5 bg-white text-black rounded-xl text-sm font-bold hover:bg-white/90 transition-all"
        >
          <Plus size={16} />
          <span>新建合集</span>
        </button>
      </div>

      {collections.length > 0 ? (
        <div className="grid grid-cols-2 gap-4">
          {collections.map((col) => (
            <div
              key={col.id}
              className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5 hover:border-white/10 transition-all cursor-pointer group"
            >
              <div className="flex items-center gap-3 mb-4">
                <div
                  className={`w-10 h-10 rounded-xl ${col.bg} flex items-center justify-center`}
                >
                  <Folder size={18} className={col.color} />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-semibold text-white truncate">
                    {col.name}
                  </h3>
                  <p className="text-xs text-slate-500">{col.count} 个播客</p>
                </div>
                <button className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-white/5 text-slate-500 hover:text-white transition-all">
                  <MoreHorizontal size={16} />
                </button>
              </div>
              <div className="space-y-2">
                {col.items.map((item, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs text-slate-400">
                    <Headphones size={12} />
                    <span className="truncate">{item}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Empty State */
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
            <Folder size={28} className="text-slate-600" />
          </div>
          <h3 className="text-white font-semibold mb-1">还没有合集</h3>
          <p className="text-sm text-slate-500 mb-6">创建合集来整理你的播客</p>
          <button
            onClick={handleAdd}
            className="px-4 py-2.5 bg-white text-black rounded-xl text-sm font-bold"
          >
            新建合集
          </button>
        </div>
      )}
    </div>
  );
}
