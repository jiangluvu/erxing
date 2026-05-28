import { useState } from "react";
import { User, AlertTriangle, Loader2, ArrowLeft } from "lucide-react";
import { useAppStore } from "../store";

export default function AccountPage() {
  const setPage = useAppStore((s) => s.setPage);
  const userName = useAppStore((s) => s.userName);
  const genCount = useAppStore((s) => s.genCount);
  const showToast = useAppStore((s) => s.showToast);
  const [clearing, setClearing] = useState(false);

  const handleClearAll = async () => {
    if (!window.confirm("确定要清除所有数据吗？此操作不可撤销。")) return;
    setClearing(true);
    try {
      const resp = await fetch("/api/clear_all", { method: "POST" });
      if (resp.ok) {
        showToast("所有数据已清除", "success");
        window.location.reload();
      } else {
        showToast("清除失败", "error");
      }
    } catch (e) {
      showToast("清除失败", "error");
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="p-10 max-w-2xl mx-auto">
      <div className="flex items-center gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">账号信息</h1>
          <p className="text-sm text-slate-500 mt-1">管理你的账号与数据</p>
        </div>
      </div>

      {/* Profile */}
      <div className="mb-8">
        <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <User size={16} className="text-brand-pink" />
          个人资料
        </h2>
        <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
          <div className="flex items-center gap-4 mb-5">
            <div className="w-12 h-12 rounded-full bg-brand-pink/10 flex items-center justify-center text-brand-pink font-bold text-lg">
              {userName?.[0] || "U"}
            </div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-white">{userName}</div>
              <div className="text-xs text-slate-500">免费用户 · 已生成 {genCount} 个播客</div>
            </div>
            <button className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-xs text-white transition-all border border-white/5">
              编辑资料
            </button>
          </div>
        </div>
      </div>

      {/* Danger Zone */}
      <div>
        <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <AlertTriangle size={16} className="text-red-400" />
          危险操作
        </h2>
        <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-white">清除所有数据</div>
              <div className="text-xs text-slate-500 mt-0.5">
                删除所有生成的播客、历史记录与设置
              </div>
            </div>
            <button
              onClick={handleClearAll}
              disabled={clearing}
              className="px-3 py-1.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-xs text-red-400 transition-all border border-red-500/20 disabled:opacity-50"
            >
              {clearing ? (
                <span className="flex items-center gap-1">
                  <Loader2 size={12} className="animate-spin" />
                  清除中...
                </span>
              ) : (
                "清除"
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
