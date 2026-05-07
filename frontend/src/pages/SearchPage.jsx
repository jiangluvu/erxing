import { useState, useMemo } from "react";
import { Search, Library, Headphones, Play, FileText, Rss } from "lucide-react";
import { useAppStore } from "../store";
import { search } from "../api";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const setPage = useAppStore((s) => s.setPage);

  const doSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await search(query.trim());
      setResults(data);
    } catch {
      setResults({ podcasts: [], articles: [], subscriptions: [] });
    }
    setLoading(false);
  };

  const podcasts = results?.podcasts || [];
  const articles = results?.articles || [];
  const subs = results?.subscriptions || [];

  return (
    <div className="p-10 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-2">全局搜索</h1>
      <p className="text-sm text-slate-500 mb-6">搜索你生成的播客、订阅源或推荐内容</p>

      {/* Search Input */}
      <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-1 flex items-center gap-2 mb-8">
        <div className="flex-1 flex items-center gap-3 px-4">
          <Search size={18} className="text-slate-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="输入关键词搜索…"
            className="w-full bg-transparent text-sm text-white placeholder-slate-600 outline-none py-3"
            onKeyDown={(e) => e.key === "Enter" && doSearch()}
          />
        </div>
        <button
          onClick={doSearch}
          disabled={loading}
          className="px-5 py-2.5 bg-white text-black rounded-xl text-sm font-bold hover:bg-white/90 transition-all disabled:opacity-50"
        >
          {loading ? "搜索中…" : "搜索"}
        </button>
      </div>

      {/* Results */}
      {results ? (
        <div className="space-y-8">
          {podcasts.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Library size={16} className="text-brand-pink" />
                <h2 className="text-sm font-semibold text-white">播客</h2>
                <span className="text-xs text-slate-500">{podcasts.length} 个结果</span>
              </div>
              <div className="space-y-2">
                {podcasts.map((p) => (
                  <div
                    key={p.id}
                    className="flex items-center gap-4 bg-[#161618] border border-[#2a2a2a] rounded-2xl p-4 hover:border-white/10 transition-all cursor-pointer"
                    onClick={() => setPage("player")}
                  >
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-brand-pink/20 to-brand-tertiary/20 flex items-center justify-center flex-shrink-0">
                      <Headphones size={20} className="text-brand-pink" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-sm font-semibold text-white truncate">{p.title}</h3>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {p.platform} · {p.duration === "short" ? "5 分钟" : p.duration === "long" ? "15 分钟" : "10 分钟"}
                      </p>
                    </div>
                    <button className="p-2 rounded-lg hover:bg-white/5 text-slate-500 hover:text-white transition-all">
                      <Play size={16} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {articles.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <FileText size={16} className="text-brand-tertiary" />
                <h2 className="text-sm font-semibold text-white">文章</h2>
                <span className="text-xs text-slate-500">{articles.length} 个结果</span>
              </div>
              {articles.map((a) => (
                <div
                  key={a.id || a.title}
                  className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-4 hover:border-white/10 transition-all cursor-pointer"
                >
                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-[10px] px-2 py-0.5 rounded bg-white/5 text-slate-500 border border-white/5">
                      {a.platform}
                    </span>
                  </div>
                  <h3 className="text-sm font-semibold text-white mb-1">{a.title}</h3>
                  <p className="text-xs text-slate-500 line-clamp-2">{a.desc}</p>
                </div>
              ))}
            </div>
          )}

          {subs.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Rss size={16} className="text-[#5E9EFF]" />
                <h2 className="text-sm font-semibold text-white">订阅源</h2>
                <span className="text-xs text-slate-500">{subs.length} 个结果</span>
              </div>
              {subs.map((s) => (
                <div
                  key={s.id}
                  className="flex items-center gap-4 bg-[#161618] border border-[#2a2a2a] rounded-2xl p-4 hover:border-white/10 transition-all cursor-pointer"
                >
                  <div className="w-10 h-10 rounded-xl bg-brand-pink/10 flex items-center justify-center flex-shrink-0">
                    <FileText size={18} className="text-brand-pink" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-semibold text-white">{s.name}</h3>
                    <p className="text-xs text-slate-500">{s.platform}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {podcasts.length === 0 && articles.length === 0 && subs.length === 0 && (
            <div className="text-center py-12">
              <p className="text-sm text-slate-500">未找到与 "{query}" 相关的内容</p>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-12">
          <Search size={32} className="text-slate-700 mx-auto mb-3" />
          <p className="text-sm text-slate-500">输入关键词开始搜索</p>
        </div>
      )}
    </div>
  );
}
