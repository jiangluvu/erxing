import { useState, useEffect } from "react";
import {
  Link,
  MessageSquare,
  PlayCircle,
  FileText,
  Settings2,
  Trash2,
  Rss,
} from "lucide-react";
import { useAppStore } from "../store";
import { getSubscriptions, addSubscription, deleteSubscription, updateSubscription } from "../api";

const platformMeta = {
  公众号: { icon: MessageSquare, color: "text-brand-pink", bg: "bg-brand-pink/10" },
  B站: { icon: PlayCircle, color: "text-[#5E9EFF]", bg: "bg-[#5E9EFF]/10" },
  知乎: { icon: FileText, color: "text-slate-500", bg: "bg-white/5" },
};

const mockSubs = [
  {
    id: "1",
    name: "晚点LatePost",
    platform: "公众号",
    lastGen: "2026-05-03",
    total: 12,
    active: true,
  },
  {
    id: "2",
    name: "影视飓风",
    platform: "B站",
    lastGen: "2026-05-02",
    total: 8,
    active: true,
  },
  {
    id: "3",
    name: "知乎日报",
    platform: "知乎",
    lastGen: "2026-04-28",
    total: 3,
    active: false,
  },
];

export default function SubscriptionPage() {
  const [url, setUrl] = useState("");
  const [subs, setSubs] = useState(mockSubs);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState("");
  const [editAuto, setEditAuto] = useState(false);
  const [toast, setToast] = useState("");
  const setPage = useAppStore((s) => s.setPage);

  useEffect(() => {
    getSubscriptions()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) setSubs(data);
      })
      .catch(() => {});
  }, []);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 2000);
  };

  const handleAdd = async () => {
    if (!url.trim()) return;
    setLoading(true);
    try {
      await addSubscription(url.trim());
      const data = await getSubscriptions();
      if (Array.isArray(data)) setSubs(data);
      setUrl("");
    } catch {
      setSubs((prev) => [
        ...prev,
        {
          id: String(Date.now()),
          name: url.trim(),
          platform: "公众号",
          lastGen: "刚刚",
          total: 0,
          active: true,
        },
      ]);
      setUrl("");
    }
    setLoading(false);
  };

  const handleDelete = async (id) => {
    try {
      await deleteSubscription(id);
      setSubs((prev) => prev.filter((s) => s.id !== id));
    } catch {
      setSubs((prev) => prev.filter((s) => s.id !== id));
    }
  };

  const openEdit = (sub) => {
    setEditingId(sub.id);
    setEditName(sub.name || "");
    setEditAuto(!!sub.auto_generate);
  };

  const closeEdit = () => {
    setEditingId(null);
    setEditName("");
    setEditAuto(false);
  };

  const handleEditSave = async () => {
    if (!editName.trim()) {
      showToast("名称不能为空");
      return;
    }
    try {
      await updateSubscription(editingId, { name: editName.trim(), auto_generate: editAuto });
      setSubs((prev) =>
        prev.map((s) =>
          s.id === editingId ? { ...s, name: editName.trim(), auto_generate: editAuto } : s
        )
      );
      showToast("订阅已更新");
      closeEdit();
    } catch {
      showToast("更新失败");
    }
  };

  return (
    <div className="p-10 max-w-3xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">内容源订阅</h1>
        <p className="text-sm text-slate-500 mt-1">
          订阅你关注的内容源，自动同步生成播客
        </p>
      </div>

      {/* Add Input */}
      <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-1 flex items-center gap-2 mb-8">
        <div className="flex-1 flex items-center gap-3 px-4">
          <Link size={16} className="text-slate-500" />
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="粘贴公众号 / B站 / 知乎 / RSS 链接…"
            className="w-full bg-transparent text-sm text-white placeholder-slate-600 outline-none py-3"
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          />
        </div>
        <button
          onClick={handleAdd}
          disabled={loading}
          className="px-5 py-2.5 bg-white text-black rounded-xl text-sm font-bold hover:bg-white/90 transition-all disabled:opacity-50"
        >
          {loading ? "订阅中…" : "订阅"}
        </button>
      </div>

      {/* List */}
      {subs.length > 0 ? (
        <div className="space-y-3">
          {subs.map((sub) => {
            const meta = platformMeta[sub.platform] || platformMeta["知乎"];
            const Icon = meta.icon;
            return (
              <div
                key={sub.id}
                className="flex items-center gap-4 bg-[#161618] border border-[#2a2a2a] rounded-2xl p-4 hover:border-white/10 transition-all"
              >
                <div
                  className={`w-10 h-10 rounded-xl ${meta.bg} flex items-center justify-center flex-shrink-0`}
                >
                  <Icon size={18} className={meta.color} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <h3 className="text-sm font-semibold text-white truncate">
                      {sub.name}
                    </h3>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-500 border border-white/5">
                      {sub.platform}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500">
                    上次生成：{sub.lastGen} · 共生成 {sub.total} 期播客
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span
                    className={`flex items-center gap-1 text-[10px] ${
                      sub.active ? "text-brand-tertiary" : "text-slate-500"
                    }`}
                  >
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${
                        sub.active ? "bg-brand-tertiary" : "bg-slate-500"
                      }`}
                    />
                    {sub.active ? "自动同步中" : "已暂停"}
                  </span>
                  <button
                    onClick={() => openEdit(sub)}
                    className="p-2 rounded-lg hover:bg-white/5 text-slate-500 hover:text-white transition-all"
                  >
                    <Settings2 size={14} />
                  </button>
                  <button
                    onClick={() => handleDelete(sub.id)}
                    className="p-2 rounded-lg hover:bg-white/5 text-slate-500 hover:text-red-400 transition-all"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Empty State */
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
            <Rss size={28} className="text-slate-600" />
          </div>
          <h3 className="text-white font-semibold mb-1">还没有订阅</h3>
          <p className="text-sm text-slate-500 mb-6">
            订阅你喜欢的内容源，耳行会自动为你生成播客
          </p>
        </div>
      )}

      {/* Edit Modal */}
      {editingId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-6 w-full max-w-sm mx-4">
            <h3 className="text-white font-semibold mb-4">编辑订阅</h3>
            <div className="mb-4">
              <label className="block text-xs text-slate-500 mb-1">名称</label>
              <input
                type="text"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="w-full bg-[#0c0c0e] border border-[#2a2a2a] rounded-xl px-3 py-2 text-sm text-white outline-none focus:border-brand-pink"
              />
            </div>
            <div className="flex items-center gap-2 mb-6">
              <input
                id="editAuto"
                type="checkbox"
                checked={editAuto}
                onChange={(e) => setEditAuto(e.target.checked)}
                className="accent-brand-pink"
              />
              <label htmlFor="editAuto" className="text-sm text-slate-400">自动同步生成播客</label>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleEditSave}
                className="flex-1 py-2.5 bg-white text-black rounded-xl text-sm font-bold hover:bg-white/90 transition-all"
              >
                保存
              </button>
              <button
                onClick={closeEdit}
                className="flex-1 py-2.5 bg-white/5 text-white rounded-xl text-sm hover:bg-white/10 transition-all"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 bg-[#1a1a1c] border border-[#2a2a2a] text-white text-sm px-5 py-2.5 rounded-xl shadow-lg z-50">
          {toast}
        </div>
      )}
    </div>
  );
}
