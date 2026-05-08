import { useState, useEffect } from "react";
import { Plus, Folder, Headphones, MoreHorizontal, Trash2 } from "lucide-react";
import {
  getCollections,
  addCollection,
  deleteCollection,
} from "../api";

export default function CollectionsPage() {
  const [collections, setCollections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [newName, setNewName] = useState("");

  useEffect(() => {
    getCollections()
      .then((data) => {
        setCollections(data?.collections || []);
      })
      .catch(() => setCollections([]))
      .finally(() => setLoading(false));
  }, []);

  const handleAdd = async () => {
    if (!newName?.trim()) return;
    try {
      const data = await addCollection({ name: newName.trim() });
      setCollections(data?.collections || []);
    } catch {
      setCollections((prev) => [
        ...prev,
        {
          id: String(Date.now()),
          name: newName.trim(),
          session_ids: [],
          created_at: new Date().toISOString(),
        },
      ]);
    }
    setNewName("");
    setShowModal(false);
  };

  const handleDelete = async (id) => {
    try {
      await deleteCollection(id);
      setCollections((prev) => prev.filter((c) => c.id !== id));
    } catch {
      setCollections((prev) => prev.filter((c) => c.id !== id));
    }
  };

  return (
    <div className="p-10 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">我的合集</h1>
          <p className="text-sm text-slate-500 mt-1">整理你的播客，按主题归类</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-white text-black rounded-xl text-sm font-bold hover:bg-white/90 transition-all"
        >
          <Plus size={16} />
          <span>新建合集</span>
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-sm text-slate-500">加载中…</div>
      ) : collections.length > 0 ? (
        <div className="grid grid-cols-2 gap-4">
          {collections.map((col, i) => (
            <div
              key={col.id}
              className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5 hover:border-white/10 transition-all cursor-pointer group"
            >
              <div className="flex items-center gap-3 mb-4">
                <div
                  className={`w-10 h-10 rounded-xl ${
                    i % 2 === 0 ? "bg-brand-pink/10" : "bg-brand-tertiary/10"
                  } flex items-center justify-center`}
                >
                  <Folder
                    size={18}
                    className={i % 2 === 0 ? "text-brand-pink" : "text-brand-tertiary"}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-semibold text-white truncate">{col.name}</h3>
                  <p className="text-xs text-slate-500">
                    {(col.session_ids || []).length} 个播客
                  </p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(col.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-white/5 text-slate-500 hover:text-red-400 transition-all"
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <div className="space-y-2">
                {(col.session_ids || []).slice(0, 3).map((sid, idx) => (
                  <div key={idx} className="flex items-center gap-2 text-xs text-slate-400">
                    <Headphones size={12} />
                    <span className="truncate">{sid}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
            <Folder size={28} className="text-slate-600" />
          </div>
          <h3 className="text-white font-semibold mb-1">还没有合集</h3>
          <p className="text-sm text-slate-500 mb-6">创建合集来整理你的播客</p>
          <button
            onClick={() => setShowModal(true)}
            className="px-4 py-2.5 bg-white text-black rounded-xl text-sm font-bold"
          >
            新建合集
          </button>
        </div>
      )}

      {/* Add Collection Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-6 w-full max-w-sm">
            <h3 className="text-white font-semibold mb-4">新建合集</h3>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleAdd();
                if (e.key === "Escape") setShowModal(false);
              }}
              placeholder="输入合集名称..."
              className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-xl px-4 py-3 text-sm text-white placeholder-slate-600 outline-none focus:border-brand-pink/50 transition-all mb-4"
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => {
                  setShowModal(false);
                  setNewName("");
                }}
                className="px-4 py-2 rounded-lg text-xs text-slate-400 hover:text-white transition-all"
              >
                取消
              </button>
              <button
                onClick={handleAdd}
                className="px-4 py-2 bg-white text-black rounded-lg text-xs font-bold hover:bg-white/90 transition-all"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
