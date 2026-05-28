import {
  Sparkles,
  Library,
  Music,
  Mic,
  Rss,
  Flame,
  Plus,
  User,
  Clock,
  Heart,
  FileText,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { useAppStore } from "../store";

const exploreItems = [
  { id: "subscriptions", label: "订阅", icon: Rss },
  { id: "hot", label: "热门", icon: Flame },
];

const collectionItems = [
  { id: "collections", label: "新合集", icon: Plus },
];

const toolItems = [
  { id: "history", label: "历史记录", icon: Clock },
  { id: "favorites", label: "收藏", icon: Heart },
  { id: "notes", label: "笔记", icon: FileText },
];

export default function SideNavBar() {
  const currentPage = useAppStore((s) => s.currentPage);
  const setPage = useAppStore((s) => s.setPage);
  const genCount = useAppStore((s) => s.genCount);

  const isActive = (id) => currentPage === id;

  const navItems = [
    { id: "home", label: "新播客", icon: Sparkles },
    { id: "myDrafts", label: "我的草稿", icon: FileText },
    { id: "myPodcasts", label: "我的播客", icon: Library },
    { id: "workshop", label: "播客工坊", icon: Music },
    { id: "myTemplates", label: "我的模板", icon: FileText },
    { id: "myVoices", label: "我的声音", icon: Mic },
  ];

  const NavLink = ({ item }) => {
    const Icon = item.icon;
    const active = isActive(item.id);
    return (
      <button
        onClick={() => setPage(item.id)}
        className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-all text-left ${
          active
            ? "text-white bg-white/5 font-medium"
            : "text-slate-400 hover:text-white hover:bg-white/5"
        }`}
      >
        <Icon
          size={18}
          className={active ? "text-brand-pink" : ""}
          strokeWidth={2}
        />
        <span className="flex-1">{item.label}</span>
        {item.badge && (
          <span className="text-[10px] text-slate-500">({item.badge})</span>
        )}
      </button>
    );
  };

  return (
    <aside className="fixed left-0 top-0 h-full w-[240px] bg-[#1a1a1a] border-r border-[#2a2a2a] flex flex-col z-50">
      <div className="p-6 flex-1 overflow-y-auto">
        <h2 className="text-xs font-medium text-slate-500 mb-6">
          欢迎 播刻 新用户!
        </h2>
        <div className="flex items-center gap-3 mb-8">
          <span className="text-2xl font-black text-brand-pink">播刻</span>
          <span className="bg-brand-pink/10 text-brand-pink text-[10px] px-2 py-0.5 rounded-full font-bold">
            PRO
          </span>
        </div>

        <nav className="space-y-1">
          {navItems.map((item) => (
            <NavLink key={item.id} item={item} />
          ))}
        </nav>

        <div className="mt-6">
          <h3 className="px-3 text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-2">
            探索
          </h3>
          <nav className="space-y-1">
            {exploreItems.map((item) => (
              <NavLink key={item.id} item={item} />
            ))}
          </nav>
        </div>

        <div className="mt-6">
          <h3 className="px-3 text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-2">
            合集
          </h3>
          <nav className="space-y-1">
            {collectionItems.map((item) => (
              <NavLink key={item.id} item={item} />
            ))}
            <div className="px-3 py-4 text-xs text-slate-600 italic">
              暂无合集
            </div>
          </nav>
        </div>

        <div className="mt-6">
          <h3 className="px-3 text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-2">
            工具
          </h3>
          <nav className="space-y-1">
            {toolItems.map((item) => (
              <NavLink key={item.id} item={item} />
            ))}
          </nav>
        </div>
      </div>

      {/* Generation Progress */}
      <GenerationProgress />

      <div className="p-4 border-t border-[#2a2a2a]">
        <button
          onClick={() => setPage("account")}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-all text-left ${
            isActive("account")
              ? "text-white bg-white/5 font-medium"
              : "text-slate-400 hover:text-white hover:bg-white/5"
          }`}
        >
          <User size={18} strokeWidth={2} className={isActive("account") ? "text-brand-pink" : ""} />
          <span>账号信息</span>
        </button>
      </div>
    </aside>
  );
}

function GenerationProgress() {
  const status = useAppStore((s) => s.generationStatus);
  const progress = useAppStore((s) => s.generationProgress);
  const statusText = useAppStore((s) => s.statusText);
  const sessionId = useAppStore((s) => s.sessionId);
  const setPage = useAppStore((s) => s.setPage);
  const setGenerationStatus = useAppStore((s) => s.setGenerationStatus);

  if (status === "idle") return null;

  return (
    <div className="px-4 py-3 border-t border-[#2a2a2a]">
      <div
        onClick={() => {
          if (status === "complete" || status === "failed") {
            setGenerationStatus("idle");
          } else {
            setPage("home");
          }
        }}
        className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/5 cursor-pointer hover:bg-white/10 transition-all"
      >
        {status === "generating" && <Loader2 size={14} className="animate-spin text-brand-pink" />}
        {status === "complete" && <CheckCircle2 size={14} className="text-green-500" />}
        {status === "failed" && <AlertCircle size={14} className="text-red-500" />}
        <div className="flex-1 min-w-0">
          <div className="text-[10px] text-slate-400 truncate">{statusText || "生成中…"}</div>
          {status === "generating" && (
            <div className="mt-1 h-1 bg-[#2a2a2a] rounded-full overflow-hidden">
              <div className="h-full bg-brand-pink rounded-full transition-all" style={{ width: `${Math.max(2, progress)}%` }} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
