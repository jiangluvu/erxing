import { useState, useEffect } from "react";
import { PenLine, Trash2, Pencil } from "lucide-react";
import { getNotes, addNote, deleteNote, updateNote } from "../api";

const mockNotes = [
  {
    id: "1",
    title: "AI 教育的关键论点",
    content:
      '作者提到的"个性化学习"概念很有意思，但隐私问题也不容忽视。需要在产品设计中平衡这两者。',
    source: "AI 时代的数字生活变革",
    time: "3 天前",
  },
  {
    id: "2",
    title: "FSD 入华的时间线",
    content:
      "2024年4月宣布，2026年Q1正式落地。本土企业的反应速度会决定市场格局。",
    source: "特斯拉 FSD 入华",
    time: "1 周前",
  },
];

export default function NotesPage() {
  const [notes, setNotes] = useState(mockNotes);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [toast, setToast] = useState("");

  useEffect(() => {
    getNotes()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) setNotes(data);
      })
      .catch(() => {});
  }, []);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 2000);
  };

  const handleSave = async () => {
    if (!content.trim()) return;
    setSaving(true);
    try {
      await addNote({ session_id: "mock", title: title.trim(), content: content.trim() });
      const data = await getNotes();
      if (Array.isArray(data)) setNotes(data);
      setTitle("");
      setContent("");
    } catch {
      setNotes((prev) => [
        {
          id: String(Date.now()),
          title: title.trim() || "未命名笔记",
          content: content.trim(),
          source: "当前播客",
          time: "刚刚",
        },
        ...prev,
      ]);
      setTitle("");
      setContent("");
    }
    setSaving(false);
  };

  const handleDelete = async (id) => {
    try {
      await deleteNote(id);
      setNotes((prev) => prev.filter((n) => n.id !== id));
    } catch {
      setNotes((prev) => prev.filter((n) => n.id !== id));
    }
  };

  const openEdit = (note) => {
    setEditingId(note.id);
    setEditTitle(note.title || "");
    setEditContent(note.content || "");
  };

  const closeEdit = () => {
    setEditingId(null);
    setEditTitle("");
    setEditContent("");
  };

  const handleEditSave = async () => {
    if (!editContent.trim()) {
      showToast("内容不能为空");
      return;
    }
    try {
      await updateNote(editingId, { title: editTitle.trim(), content: editContent.trim() });
      setNotes((prev) =>
        prev.map((n) =>
          n.id === editingId ? { ...n, title: editTitle.trim(), content: editContent.trim() } : n
        )
      );
      showToast("笔记已更新");
      closeEdit();
    } catch {
      showToast("更新失败");
    }
  };

  return (
    <div className="p-10 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-2">笔记</h1>
      <p className="text-sm text-slate-500 mb-6">记录播客中的灵感与思考</p>

      {/* Add Note */}
      <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-4 mb-6">
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="笔记标题（选填）"
          className="w-full bg-transparent text-sm text-white placeholder-slate-600 outline-none mb-3 font-semibold"
        />
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="写笔记…"
          className="w-full bg-transparent text-sm text-white placeholder-slate-600 outline-none resize-none h-20 leading-relaxed"
        />
        <div className="flex items-center justify-between pt-3 border-t border-[#2a2a2a] mt-3">
          <div className="text-xs text-slate-500">关联播客：AI 时代的数字生活变革</div>
          <button
            onClick={handleSave}
            disabled={saving || !content.trim()}
            className="px-4 py-2 bg-white text-black rounded-xl text-xs font-bold hover:bg-white/90 transition-all disabled:opacity-50"
          >
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>

      {/* Notes List */}
      {notes.length > 0 ? (
        <div className="space-y-3">
          {notes.map((note) => (
            <div
              key={note.id}
              className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5 hover:border-white/10 transition-all group"
            >
              <div className="flex items-start justify-between mb-2">
                <h3 className="text-sm font-semibold text-white">{note.title || "未命名笔记"}</h3>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => openEdit(note)}
                    className="p-1.5 rounded-lg hover:bg-white/5 text-slate-500 hover:text-white transition-all"
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    onClick={() => handleDelete(note.id)}
                    className="p-1.5 rounded-lg hover:bg-white/5 text-slate-500 hover:text-red-400 transition-all"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <p className="text-sm text-slate-400 leading-relaxed mb-3">
                {note.content}
              </p>
              <div className="flex items-center gap-3 text-xs text-slate-500">
                <span>来自：{note.source}</span>
                <span>·</span>
                <span>{note.time}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Empty State */
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
            <PenLine size={28} className="text-slate-600" />
          </div>
          <h3 className="text-white font-semibold mb-1">还没有笔记</h3>
          <p className="text-sm text-slate-500 mb-6">
            在播放器中记录灵感，或在这里直接创建笔记
          </p>
        </div>
      )}
    </div>
  );
}
