import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { ArrowLeft, Loader2 } from "lucide-react";
import { useAppStore } from "../store";
import { getDashboardMetrics } from "../api";

const COLORS = ["#ec4899", "#52dea2", "#5E9EFF", "#FF9F5E", "#FFD700", "#764BA2"];

function StatCard({ label, value, sub }) {
  return (
    <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {sub && <div className="text-[10px] text-slate-600 mt-1">{sub}</div>}
    </div>
  );
}

export default function MonitorPage() {
  const setPage = useAppStore((s) => s.setPage);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);

  useEffect(() => {
    setLoading(true);
    getDashboardMetrics(days)
      .then((res) => setData(res))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [days]);

  const input = data?.input_layer || {};
  const gen = data?.generation_quality || {};
  const tts = data?.tts || {};
  const playback = data?.playback || {};

  const sourceData = Object.entries(input.source_distribution || {}).map(([k, v]) => ({
    name: k === "url" ? "URL" : k === "text" ? "文本" : k === "upload" ? "上传" : k,
    value: v,
  }));

  const trendData = (gen.daily_trend || []).map((d) => ({
    date: d.date?.slice(5) || d.date,
    coverage: Math.round((d.coverage || 0) * 100),
    faithfulness: Math.round((d.faithfulness || 0) * 100),
    turns: d.turns || 0,
  }));

  const emotionData = Object.entries(tts.emotion_distribution || {}).map(([k, v]) => ({
    name: k,
    value: v,
  }));

  const exitData = (playback.top_exit_turns || []).map((t) => ({
    name: `Turn ${t.turn_index + 1}`,
    exits: t.exit_count,
    avgListen: t.avg_listen_duration_s,
  }));

  return (
    <div className="p-10 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-xl font-bold text-white">数据监控中心</h1>
            <p className="text-xs text-slate-500 mt-1">
              输入层 · 生成质量 · TTS · 播放行为
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {[7, 14, 30].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                days === d
                  ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                  : "bg-white/5 text-slate-400 border border-transparent hover:bg-white/10"
              }`}
            >
              近{d}天
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={32} className="text-brand-pink animate-spin" />
        </div>
      ) : (
        <div className="space-y-8">
          {/* Input Layer */}
          <section>
            <h2 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
              <span className="w-1 h-4 bg-brand-pink rounded-full" />
              输入层概览
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <StatCard label="总文章数" value={input.total_articles || 0} />
              <StatCard
                label="平均长度"
                value={`${input.avg_article_length || 0} 字`}
              />
              <StatCard
                label="解析失败率"
                value={`${Math.round((input.parse_failure_rate || 0) * 100)}%`}
              />
              <StatCard
                label="来源最多"
                value={
                  Object.entries(input.platform_distribution || {}).sort(
                    (a, b) => b[1] - a[1]
                  )[0]?.[0] || "—"
                }
              />
            </div>
            {sourceData.length > 0 && (
              <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
                <div className="text-xs text-slate-500 mb-3">来源分布</div>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie
                      data={sourceData}
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={80}
                      dataKey="value"
                      nameKey="name"
                    >
                      {sourceData.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: "#1a1a1c",
                        border: "1px solid #2a2a2a",
                        borderRadius: 8,
                        color: "#fff",
                      }}
                    />
                    <Legend
                      wrapperStyle={{ color: "#94a3b8" }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>

          {/* Generation Quality */}
          <section>
            <h2 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
              <span className="w-1 h-4 bg-brand-tertiary rounded-full" />
              生成质量趋势
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <StatCard
                label="平均关键词覆盖"
                value={`${Math.round((gen.avg_keyword_coverage || 0) * 100)}%`}
              />
              <StatCard
                label="平均忠实度"
                value={`${Math.round((gen.avg_faithfulness || 0) * 100)}%`}
              />
              <StatCard
                label="角色区分度"
                value={`${Math.round((gen.avg_role_distinction || 0) * 100)}%`}
              />
              <StatCard
                label="格式失败率"
                value={`${Math.round((gen.format_failure_rate || 0) * 100)}%`}
              />
            </div>
            {trendData.length > 0 && (
              <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
                <div className="text-xs text-slate-500 mb-3">每日趋势</div>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={trendData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
                    <XAxis dataKey="date" stroke="#64748b" fontSize={12} />
                    <YAxis stroke="#64748b" fontSize={12} />
                    <Tooltip
                      contentStyle={{
                        background: "#1a1a1c",
                        border: "1px solid #2a2a2a",
                        borderRadius: 8,
                        color: "#fff",
                      }}
                    />
                    <Legend wrapperStyle={{ color: "#94a3b8" }} />
                    <Line
                      type="monotone"
                      dataKey="coverage"
                      name="关键词覆盖%"
                      stroke="#ec4899"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="faithfulness"
                      name="忠实度%"
                      stroke="#52dea2"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>

          {/* TTS */}
          <section>
            <h2 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
              <span className="w-1 h-4 bg-[#5E9EFF] rounded-full" />
              TTS 质量
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <StatCard label="TTS 会话数" value={tts.total_sessions || 0} />
              <StatCard
                label="失败率"
                value={`${Math.round((tts.failure_rate || 0) * 100)}%`}
              />
              <StatCard
                label="平均耗时"
                value={`${Math.round(tts.avg_tts_time_ms || 0)}ms`}
              />
              <StatCard
                label="主要情绪"
                value={
                  Object.entries(tts.emotion_distribution || {}).sort(
                    (a, b) => b[1] - a[1]
                  )[0]?.[0] || "—"
                }
              />
            </div>
            {emotionData.length > 0 && (
              <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
                <div className="text-xs text-slate-500 mb-3">情绪分布</div>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={emotionData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
                    <XAxis dataKey="name" stroke="#64748b" fontSize={12} />
                    <YAxis stroke="#64748b" fontSize={12} />
                    <Tooltip
                      contentStyle={{
                        background: "#1a1a1c",
                        border: "1px solid #2a2a2a",
                        borderRadius: 8,
                        color: "#fff",
                      }}
                    />
                    <Bar dataKey="value" fill="#ec4899" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>

          {/* Playback */}
          <section>
            <h2 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
              <span className="w-1 h-4 bg-[#FF9F5E] rounded-full" />
              播放热力图
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
              <StatCard
                label="平均完播率"
                value={`${Math.round((playback.avg_completion_rate || 0) * 100)}%`}
              />
              <StatCard
                label="平均收听时长"
                value={`${Math.round(playback.avg_listen_duration_s || 0)}s`}
              />
              <StatCard
                label="最高退出 Turn"
                value={`#${(playback.top_exit_turns || [])[0]?.turn_index + 1 || "—"}`}
              />
            </div>
            {exitData.length > 0 && (
              <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
                <div className="text-xs text-slate-500 mb-3">
                  用户退出最多的 Turn（Top 10）
                </div>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={exitData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
                    <XAxis type="number" stroke="#64748b" fontSize={12} />
                    <YAxis
                      dataKey="name"
                      type="category"
                      stroke="#64748b"
                      fontSize={12}
                      width={80}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#1a1a1c",
                        border: "1px solid #2a2a2a",
                        borderRadius: 8,
                        color: "#fff",
                      }}
                    />
                    <Legend wrapperStyle={{ color: "#94a3b8" }} />
                    <Bar
                      dataKey="exits"
                      name="退出次数"
                      fill="#ec4899"
                      radius={[0, 4, 4, 0]}
                    />
                    <Bar
                      dataKey="avgListen"
                      name="平均停留(s)"
                      fill="#52dea2"
                      radius={[0, 4, 4, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
