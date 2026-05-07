import {
  Sparkles,
  Search,
  Library,
  Headphones,
  Rss,
  Flame,
  Plus,
  LogIn,
  Folder,
  Clock,
  Heart,
  FileText,
  Settings,
} from "lucide-react";
import { useAppStore } from "../store";

const navItems = [
  { id: "home", label: "新播客", icon: Sparkles },
  { id: "search", label: "全局搜索", icon: Search },
  { id: "myPodcasts", label: "我的播客", icon: Library, badge: "3" },
  { id: "output", label: "产出物", icon: Headphones },
];

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
  { id: "settings", label: "设置", icon: Settings },
];

export default function SideNavBar() {
  const currentPage = useAppStore((s) => s.currentPage);
  const setPage = useAppStore((s) => s.setPage);
  const genCount = useAppStore((s) => s.genCount);

  const isActive = (id) => currentPage === id;

  const navItems = [
    { id: "home", label: "新播客", icon: Sparkles },
    { id: "search", label: "全局搜索", icon: Search },
    { id: "myPodcasts", label: "我的播客", icon: Library, badge: String(genCount) },
    { id: "output", label: "产出物", icon: Headphones },
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
      <div className="p-6">
        <h2 className="text-xs font-medium text-slate-500 mb-6">
          欢迎 耳行 新用户!
        </h2>
        <div className="flex items-center gap-3 mb-8">
          <span className="text-2xl font-black text-brand-pink">耳行</span>
          <span className="bg-brand-pink/10 text-brand-pink text-[10px] px-2 py-0.5 rounded-full font-bold">
            PRO
          </span>
        </div>

        <nav className="space-y-1">
          {navItems.map((item) => (
            <NavLink key={item.id} item={item} />
          ))}
        </nav>

        <div className="mt-8">
          <h3 className="px-3 text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-2">
            探索
          </h3>
          <nav className="space-y-1">
            {exploreItems.map((item) => (
              <NavLink key={item.id} item={item} />
            ))}
          </nav>
        </div>

        <div className="mt-8">
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

        <div className="mt-8">
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

      <div className="mt-auto p-4 border-t border-[#2a2a2a]">
        <button
          onClick={() => setPage("login")}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-white/5 hover:bg-white/10 text-white rounded-xl text-sm font-medium transition-all"
        >
          <LogIn size={18} strokeWidth={2} />
          <span>注册 / 登录</span>
        </button>
      </div>
    </aside>
  );
}
