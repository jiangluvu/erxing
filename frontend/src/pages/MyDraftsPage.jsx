import { useState } from "react";
import {
  FileText,
  Trash2,
  Sparkles,
  AlertCircle,
  Loader2,
  Clock,
} from "lucide-react";
import { useAppStore } from "../store";
import { generateTTS } from "../api";

function formatTime(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hour = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${month}-${day} ${hour}:${min}`;
}

function previewText(script) {
  if (!script || !script.length) return "空文稿";
  const first = script[0]?.text || "";
  return first.slice(0, 60) + (first.length > 60 ? "..." : "");
}

export default function MyDraftsPage() {
  const drafts = useAppStore((s) => s.drafts);
  const deleteDraft = useAppStore((s) => s.deleteDraft);
  const setScriptData = useAppStore((s) => s.setScriptData);
  const setPage = useAppStore((s) => s.setPage);
  const showToast = useAppStore((s) => s.showToast);
  const maleVoiceId = useAppStore((s) => s.maleVoiceId);
  const femaleVoiceId = useAppStore((s) => s.femaleVoiceId);
  const setFullAudioUrl = useAppStore((s) => s.setFullAudioUrl);
  const setSessionId = useAppStore((s) => s.setSessionId);
  const setCurrentDraftId = useAppStore((s) => s.setCurrentDraftId);
  const [synthId, setSynthId] = useState(null);

  const handleEdit = (draft) => {
    setScriptData(draft.script);
    setCurrentDraftId(draft.id);
    setPage("scriptEditor");
  };

  const handleSynth = async (draft) => {
    setSynthId(draft.id);
    try {
      const voiceMap = { 主持: maleVoiceId, 嘉宾: femaleVoiceId };
      const payload = { script: draft.script, voice_map: voiceMap };
      const { blob, sessionId } = await generateTTS(payload);
      const url = URL.createObjectURL(blob);
      setFullAudioUrl(url);
      setSessionId(sessionId);
      useAppStore.getState().setCurrentPodcast({
        title: draft.title || "",
        platform: "网页",
        time: "刚刚",
        sessionId: sessionId,
      });
      useAppStore.getState().setGenerationStatus("complete");
      useAppStore.getState().setStatusText("播客已就绪");
      setPage("player");
      showToast("播客生成成功！", "success");
    } catch (e) {
      showToast(e.message || "语音合成失败", "error");
    } finally {
      setSynthId(null);
    }
  };

  return (
    <div className="p-10 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">我的草稿</h1>
        <p className="text-sm text-slate-500 mt-1">所有已生成的文稿草稿，可继续编辑或合成播客</p>
      </div>

      {drafts.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
            <FileText size={28} className="text-slate-600" />
          </div>
          <h3 className="text-white font-semibold mb-1">还没有草稿</h3>
          <p className="text-sm text-slate-500 mb-6">去首页生成第一篇文稿吧</p>
          <button
            onClick={() => setPage("home")}
            className="px-4 py-2.5 bg-white text-black rounded-xl text-sm font-bold hover:bg-white/90 transition-all"
          >
            开始制作
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {drafts.map((draft) => (
            <div
              key={draft.id}
              className="bg-[#161618] border border-[#2a2a2a] rounded-2xl overflow-hidden hover:border-white/10 transition-all group"
            >
              <div
                className="p-5 cursor-pointer"
                onClick={() => handleEdit(draft)}
              >
                <div className="flex items-start justify-between mb-2">
                  <h3 className="text-sm font-semibold text-white">
                    {draft.title || "我的草稿"}
                  </h3>
                  <span className="text-[10px] text-slate-500 flex items-center gap-1">
                    <Clock size={10} />
                    {formatTime(draft.updated_at || draft.created_at)}
                  </span>
                </div>
                <p className="text-xs text-slate-500 leading-relaxed line-clamp-2">
                  {previewText(draft.script)}
                </p>
                <div className="flex items-center gap-3 mt-3">
                  <span className="text-[10px] text-slate-600">
                    创建 {formatTime(draft.created_at)}
                  </span>
                  <span className="text-[10px] text-slate-600">
                    {draft.script?.length || 0} 轮对话
                  </span>
                </div>
              </div>
              <div className="px-5 py-3 border-t border-[#2a2a2a] flex items-center justify-between bg-[#1a1a1c]">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm("确定删除这篇草稿？")) deleteDraft(draft.id);
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-all"
                >
                  <Trash2 size={12} />
                  删除
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleSynth(draft);
                  }}
                  disabled={synthId === draft.id}
                  className="flex items-center gap-2 px-5 py-2 bg-brand-pink hover:bg-brand-pink/80 disabled:bg-brand-pink/40 text-white rounded-xl text-xs font-medium transition-all"
                >
                  {synthId === draft.id ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Sparkles size={12} />
                  )}
                  <span>{synthId === draft.id ? "合成中..." : "合成播客"}</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}