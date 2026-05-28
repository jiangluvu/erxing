import { useEffect, useState } from "react";
import { ArrowLeft, DollarSign, Cpu, Loader2, BarChart3, Server } from "lucide-react";
import { useAppStore } from "../store";
import { getUsageStats, getUsageModels } from "../api";

export default function UsageStatsPage() {
  const setPage = useAppStore((s) => s.setPage);
  const [stats, setStats] = useState(null);
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [days] = useState(30);

  useEffect(() => {
    Promise.all([getUsageStats(days), getUsageModels()])
      .then(([s, m]) => {
        setStats(s);
        setModels(m.models || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [days]);

  return (
    <div className="p-10 max-w-2xl mx-auto">
      <div className="flex items-center gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">API 用量</h1>
          <p className="text-sm text-slate-500 mt-1">近 {days} 天的 API 调用统计</p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="text-slate-500 animate-spin" />
        </div>
      ) : !stats || stats.total_requests === 0 ? (
        <div className="text-center py-20 text-slate-500">
          <Cpu size={40} className="mx-auto mb-4 opacity-30" />
          <p className="text-sm">暂无 API 调用记录</p>
          <p className="text-xs mt-1">生成播客后会自动记录用量数据</p>
        </div>
      ) : (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-2 gap-4 mb-8">
            <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
              <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
                <BarChart3 size={14} />
                总请求数
              </div>
              <div className="text-2xl font-bold text-white">{stats.total_requests}</div>
            </div>
            <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
              <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
                <Server size={14} />
                总 Token 数
              </div>
              <div className="text-2xl font-bold text-white">
                {(stats.total_prompt_tokens + stats.total_completion_tokens).toLocaleString()}
              </div>
              <div className="text-[11px] text-slate-600 mt-1">
                输入 {(stats.total_prompt_tokens || 0).toLocaleString()} · 输出 {(stats.total_completion_tokens || 0).toLocaleString()}
              </div>
            </div>
            <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5 col-span-2">
              <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
                <DollarSign size={14} />
                预估费用
              </div>
              <div className="text-3xl font-bold text-brand-pink">
                ${stats.total_cost.toFixed(4)}
              </div>
              <div className="text-[11px] text-slate-600 mt-1">
                按模型参考定价估算，实际费用以 API 提供商账单为准
              </div>
            </div>
          </div>

          {/* Model Breakdown */}
          <div className="mb-8">
            <h2 className="text-sm font-semibold text-white mb-3">各模型用量</h2>
            <div className="space-y-2">
              {Object.entries(stats.model_stats || {}).map(([modelId, ms]) => {
                const meta = models.find((m) => m.id === modelId);
                return (
                  <div key={modelId} className="bg-[#161618] border border-[#2a2a2a] rounded-xl p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <span className="text-sm font-semibold text-white">
                          {meta?.label || modelId}
                        </span>
                        {meta?.provider && (
                          <span className="text-[10px] text-slate-600 ml-2">{meta.provider}</span>
                        )}
                      </div>
                      <span className="text-xs text-slate-500">{ms.requests} 次请求</span>
                    </div>
                    <div className="flex gap-4 text-xs text-slate-500">
                      <span>输入 {(ms.prompt_tokens || 0).toLocaleString()} tokens</span>
                      <span>输出 {(ms.completion_tokens || 0).toLocaleString()} tokens</span>
                      <span>费用 ${ms.cost?.toFixed(4)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Daily Trend */}
          {(stats.daily_stats || []).length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-white mb-3">每日趋势</h2>
              <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-[#2a2a2a] text-slate-500">
                      <th className="text-left p-3 font-medium">日期</th>
                      <th className="text-right p-3 font-medium">请求数</th>
                      <th className="text-right p-3 font-medium">Token</th>
                      <th className="text-right p-3 font-medium">费用</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.daily_stats.slice().reverse().map((d) => (
                      <tr key={d.date} className="border-b border-[#2a2a2a]/50 text-slate-400">
                        <td className="p-3 text-white">{d.date}</td>
                        <td className="p-3 text-right">{d.requests}</td>
                        <td className="p-3 text-right">{(d.prompt_tokens + d.completion_tokens).toLocaleString()}</td>
                        <td className="p-3 text-right">${d.cost.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}