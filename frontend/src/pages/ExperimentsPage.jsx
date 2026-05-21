import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import {
  ArrowLeft,
  Loader2,
  Plus,
  FlaskConical,
  CheckCircle2,
  XCircle,
  PauseCircle,
} from "lucide-react";
import { useAppStore } from "../store";
import { getExperiments, createExperiment, getExperimentResults } from "../api";

function StatusBadge({ status }) {
  const map = {
    running: { icon: FlaskConical, cls: "text-brand-tertiary bg-brand-tertiary/10" },
    paused: { icon: PauseCircle, cls: "text-[#FF9F5E] bg-[#FF9F5E]/10" },
    completed: { icon: CheckCircle2, cls: "text-[#5E9EFF] bg-[#5E9EFF]/10" },
  };
  const s = map[status] || { icon: XCircle, cls: "text-slate-400 bg-white/5" };
  const Icon = s.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${s.cls}`}>
      <Icon size={10} />
      {status === "running" ? "运行中" : status === "paused" ? "已暂停" : status === "completed" ? "已完成" : status}
    </span>
  );
}

export default function ExperimentsPage() {
  const setPage = useAppStore((s) => s.setPage);
  const showToast = useAppStore((s) => s.showToast);
  const [experiments, setExperiments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [results, setResults] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);

  const [form, setForm] = useState({
    name: "",
    description: "",
    traffic_ratio: 0.5,
    variantA: { name: "control", weight: 0.5, config: "{}" },
    variantB: { name: "treatment", weight: 0.5, config: "{}" },
  });

  const load = () => {
    setLoading(true);
    getExperiments()
      .then((res) => setExperiments(res.experiments || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!selected) {
      setResults(null);
      return;
    }
    getExperimentResults(selected.id)
      .then((res) => setResults(res))
      .catch(() => setResults(null));
  }, [selected]);

  const handleCreate = async () => {
    if (!form.name.trim()) {
      showToast("请输入实验名称", "error");
      return;
    }
    setCreating(true);
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim(),
        traffic_ratio: parseFloat(form.traffic_ratio),
        variants: [
          { name: form.variantA.name, weight: parseFloat(form.variantA.weight), config: JSON.parse(form.variantA.config || "{}") },
          { name: form.variantB.name, weight: parseFloat(form.variantB.weight), config: JSON.parse(form.variantB.config || "{}") },
        ],
        target_metrics: ["completion_rate", "faithfulness"],
      };
      await createExperiment(payload);
      showToast("实验创建成功", "success");
      setShowCreate(false);
      setForm({
        name: "",
        description: "",
        traffic_ratio: 0.5,
        variantA: { name: "control", weight: 0.5, config: "{}" },
        variantB: { name: "treatment", weight: 0.5, config: "{}" },
      });
      load();
    } catch (e) {
      showToast(e.message || "创建失败", "error");
    } finally {
      setCreating(false);
    }
  };

  const variantNames = selected
    ? selected.variants?.map((v) => v.name) || []
    : [];

  const chartData = results?.variant_stats
    ? Object.entries(results.variant_stats).map(([name, stats]) => ({
        name,
        sampleSize: stats.sample_size || 0,
        completionRate: Math.round((stats.avg_completion_rate || 0) * 100),
        faithfulness: Math.round((stats.avg_faithfulness || 0) * 100),
        regenerationRate: Math.round((stats.avg_regeneration_rate || 0) * 100),
      }))
    : [];

  return (
    <div className="p-10 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <button
            onClick={() => setPage("home")}
            className="flex items-center gap-2 text-xs text-slate-500 hover:text-white transition-colors"
          >
            <ArrowLeft size={14} />
            返回
          </button>
          <div>
            <h1 className="text-xl font-bold text-white">实验平台</h1>
            <p className="text-xs text-slate-500 mt-1">
              创建和管理 A/B 实验，对比不同配置的效果
            </p>
          </div>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-brand-pink hover:bg-brand-pink/80 text-white rounded-xl text-sm font-bold transition-all"
        >
          <Plus size={16} />
          新建实验
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={32} className="text-brand-pink animate-spin" />
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Experiment List */}
          <div className="lg:col-span-1 space-y-3">
            <h2 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">
              实验列表
            </h2>
            {experiments.length === 0 ? (
              <div className="text-xs text-slate-600 bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
                暂无实验，点击右上角创建
              </div>
            ) : (
              experiments.map((exp) => (
                <button
                  key={exp.id}
                  onClick={() => setSelected(exp)}
                  className={`w-full text-left bg-[#161618] border rounded-2xl p-4 transition-all ${
                    selected?.id === exp.id
                      ? "border-brand-pink/30 ring-1 ring-brand-pink/20"
                      : "border-[#2a2a2a] hover:border-white/10"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-white truncate">
                      {exp.name}
                    </span>
                    <StatusBadge status={exp.status} />
                  </div>
                  <div className="text-[10px] text-slate-500">
                    {exp.variants?.length || 0} 个变体 · 流量{" "}
                    {Math.round((exp.traffic_ratio || 0) * 100)}%
                  </div>
                </button>
              ))
            )}
          </div>

          {/* Detail */}
          <div className="lg:col-span-2">
            {selected ? (
              <div className="space-y-6">
                <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-bold text-white">
                      {selected.name}
                    </h3>
                    <StatusBadge status={selected.status} />
                  </div>
                  <p className="text-xs text-slate-500 mb-4">
                    {selected.description || "无描述"}
                  </p>
                  <div className="grid grid-cols-2 gap-3">
                    {(selected.variants || []).map((v) => (
                      <div
                        key={v.name}
                        className="bg-[#1a1a1c] border border-[#2a2a2a] rounded-xl p-3"
                      >
                        <div className="text-xs font-medium text-white mb-1">
                          {v.name}
                        </div>
                        <div className="text-[10px] text-slate-500">
                          权重: {Math.round((v.weight || 0) * 100)}%
                        </div>
                        <pre className="text-[10px] text-slate-400 mt-1 overflow-x-auto">
                          {JSON.stringify(v.config, null, 2)}
                        </pre>
                      </div>
                    ))}
                  </div>
                </div>

                {results && (
                  <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
                    <h3 className="text-sm font-bold text-white mb-4">
                      实验结果
                    </h3>
                    {chartData.length > 0 ? (
                      <>
                        <div className="mb-4">
                          <ResponsiveContainer width="100%" height={220}>
                            <BarChart data={chartData}>
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
                              <Legend wrapperStyle={{ color: "#94a3b8" }} />
                              <Bar dataKey="completionRate" name="完播率%" fill="#ec4899" radius={[4, 4, 0, 0]} />
                              <Bar dataKey="faithfulness" name="忠实度%" fill="#52dea2" radius={[4, 4, 0, 0]} />
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                        <div className="space-y-2">
                          {Object.entries(results.variant_stats || {}).map(
                            ([name, stats]) => (
                              <div
                                key={name}
                                className="flex items-center justify-between bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg px-3 py-2"
                              >
                                <span className="text-xs text-white font-medium">
                                  {name}
                                </span>
                                <span className="text-[10px] text-slate-500">
                                  样本 {stats.sample_size || 0} · 完播率{" "}
                                  {Math.round((stats.avg_completion_rate || 0) * 100)}% · 忠实度{" "}
                                  {Math.round((stats.avg_faithfulness || 0) * 100)}%
                                </span>
                              </div>
                            )
                          )}
                        </div>
                      </>
                    ) : (
                      <div className="text-xs text-slate-500 py-8 text-center">
                        暂无足够数据生成对比图表
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-slate-500 py-20">
                <FlaskConical size={48} className="mb-4 opacity-20" />
                <p className="text-sm">选择一个实验查看详情</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-6">
          <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto p-6">
            <h2 className="text-sm font-bold text-white mb-4">新建实验</h2>
            <div className="space-y-4">
              <div>
                <label className="text-[10px] text-slate-500 mb-1 block">
                  实验名称
                </label>
                <input
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg py-2 px-3 text-xs text-white outline-none focus:border-brand-pink/30"
                  placeholder="例如：locked vs adaptive 短文本"
                />
              </div>
              <div>
                <label className="text-[10px] text-slate-500 mb-1 block">
                  描述
                </label>
                <textarea
                  value={form.description}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, description: e.target.value }))
                  }
                  rows={3}
                  className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg py-2 px-3 text-xs text-white outline-none focus:border-brand-pink/30 resize-none"
                  placeholder="实验目的和预期..."
                />
              </div>
              <div>
                <label className="text-[10px] text-slate-500 mb-1 block">
                  流量比例: {Math.round(form.traffic_ratio * 100)}%
                </label>
                <input
                  type="range"
                  min={0.1}
                  max={1}
                  step={0.1}
                  value={form.traffic_ratio}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      traffic_ratio: parseFloat(e.target.value),
                    }))
                  }
                  className="w-full accent-brand-pink"
                />
              </div>

              {/* Variants */}
              <div className="grid grid-cols-2 gap-3">
                {["variantA", "variantB"].map((key) => (
                  <div key={key} className="bg-[#1a1a1c] border border-[#2a2a2a] rounded-xl p-3 space-y-2">
                    <div className="text-xs font-medium text-white">
                      {key === "variantA" ? "变体 A" : "变体 B"}
                    </div>
                    <input
                      value={form[key].name}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          [key]: { ...f[key], name: e.target.value },
                        }))
                      }
                      className="w-full bg-[#161618] border border-[#2a2a2a] rounded-lg py-1.5 px-2 text-xs text-white outline-none focus:border-brand-pink/30"
                      placeholder="名称"
                    />
                    <input
                      type="number"
                      min={0}
                      max={1}
                      step={0.1}
                      value={form[key].weight}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          [key]: { ...f[key], weight: parseFloat(e.target.value) },
                        }))
                      }
                      className="w-full bg-[#161618] border border-[#2a2a2a] rounded-lg py-1.5 px-2 text-xs text-white outline-none focus:border-brand-pink/30"
                      placeholder="权重"
                    />
                    <textarea
                      value={form[key].config}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          [key]: { ...f[key], config: e.target.value },
                        }))
                      }
                      rows={3}
                      className="w-full bg-[#161618] border border-[#2a2a2a] rounded-lg py-1.5 px-2 text-xs text-white outline-none focus:border-brand-pink/30 resize-none font-mono"
                      placeholder='{"prompt_mode":"locked"}'
                    />
                  </div>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 mt-6">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 rounded-lg text-xs text-slate-400 hover:text-white transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleCreate}
                disabled={creating}
                className="flex items-center gap-2 px-5 py-2 bg-brand-pink hover:bg-brand-pink/80 disabled:bg-brand-pink/40 text-white rounded-lg text-xs font-bold transition-all"
              >
                {creating && <Loader2 size={14} className="animate-spin" />}
                创建实验
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
