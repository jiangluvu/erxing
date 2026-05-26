import { useState, useEffect, useRef } from "react";
import { Play, Pause, Loader2, ArrowLeft, Trash2, Check, ExternalLink } from "lucide-react";
import { useAppStore } from "../store";
import { saveSettingsPresets, generateTTS } from "../api";

export default function MyTemplatesPage() {
  const setPage = useAppStore((s) => s.setPage);
  const showToast = useAppStore((s) => s.showToast);

  const [introPresets, setIntroPresets] = useState([]);
  const [outroPresets, setOutroPresets] = useState([]);
  const [loading, setLoading] = useState(true);

  // TTS preview state
  const [previewingId, setPreviewingId] = useState(null);
  const [playingId, setPlayingId] = useState(null);
  const audioRef = useRef(null);

  const loadTemplates = async () => {
    setLoading(true);
    try {
      const resp = await fetch("/api/settings");
      const data = await resp.json();
      if (data.intro_presets) setIntroPresets(data.intro_presets);
      if (data.outro_presets) setOutroPresets(data.outro_presets);
    } catch {
      showToast("加载模板失败", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadTemplates(); }, []);

  // ── TTS Preview ─────────────────────────────────────────────────────

  const handlePreview = async (section, preset) => {
    const previewKey = `${section}_${preset.id || preset.name}`;
    if (playingId === previewKey) {
      audioRef.current?.pause();
      setPlayingId(null);
      return;
    }

    try {
      setPreviewingId(previewKey);
      const speaker = preset.speaker || "主持";
      const text = (preset.template || preset.text || "").replace("{topic}", "今日话题");
      const { blob } = await generateTTS({
        script: [{ speaker, text }],
        voice_map: {},
      });
      const url = URL.createObjectURL(blob);
      if (audioRef.current) {
        audioRef.current.src = url;
        audioRef.current.onended = () => setPlayingId(null);
        audioRef.current.play();
        setPlayingId(previewKey);
      }
    } catch {
      showToast("试听生成失败", "error");
    } finally {
      setPreviewingId(null);
    }
  };

  // ── Delete ──────────────────────────────────────────────────────────

  const handleDelete = async (section, presetId) => {
    if (presetId === "default") {
      showToast("默认模板不能删除", "error");
      return;
    }
    try {
      const key = `${section}_presets`;
      const updated = section === "intro"
        ? introPresets.filter((p) => p.id !== presetId)
        : outroPresets.filter((p) => p.id !== presetId);
      await saveSettingsPresets({ [key]: updated });
      if (section === "intro") setIntroPresets(updated);
      else setOutroPresets(updated);
      showToast("已删除", "success");
    } catch {
      showToast("删除失败", "error");
    }
  };

  // ── Render ──────────────────────────────────────────────────────────

  const renderPresetList = (section, presets) => (
    <div className="space-y-2">
      {presets.length === 0 ? (
        <div className="text-xs text-slate-500 bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg p-4 text-center">
          暂无模板，去「播客工坊」生成并保存
        </div>
      ) : (
        presets.map((preset) => {
          const previewKey = `${section}_${preset.id || preset.name}`;
          return (
            <div key={preset.id} className="flex items-start gap-3 bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg p-3 hover:border-white/10 transition-all">
              <div className="flex-1 min-w-0">
                <div className="text-sm text-white font-medium mb-0.5">
                  {preset.name}
                  {preset.id === "default" && (
                    <span className="ml-2 text-[10px] text-slate-500 bg-white/5 px-1.5 py-0.5 rounded">默认</span>
                  )}
                </div>
                <div className="text-xs text-slate-400 truncate leading-relaxed">
                  {preset.template || preset.text}
                </div>
                <div className="flex items-center gap-3 mt-1.5 text-[10px] text-slate-500">
                  <span>说话人: {preset.speaker || "主持"}</span>
                  {preset.transition_style && <span>风格: {preset.transition_style}</span>}
                </div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0 mt-0.5">
                <button
                  onClick={() => handlePreview(section, preset)}
                  disabled={previewingId === previewKey}
                  className="p-1.5 rounded hover:bg-white/5 text-slate-400 hover:text-white transition-colors disabled:opacity-50"
                  title="试听"
                >
                  {previewingId === previewKey ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : playingId === previewKey ? (
                    <Pause size={14} />
                  ) : (
                    <Play size={14} />
                  )}
                </button>
                <button
                  onClick={() => handleDelete(section, preset.id)}
                  className="p-1.5 rounded hover:bg-red-500/10 text-slate-400 hover:text-red-400 transition-colors"
                  title="删除"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          );
        })
      )}
    </div>
  );

  return (
    <div className="p-10 max-w-2xl mx-auto">
      <audio ref={audioRef} className="hidden" />

      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <button
          onClick={() => setPage("home")}
          className="flex items-center gap-2 text-xs text-slate-500 hover:text-white transition-colors"
        >
          <ArrowLeft size={14} />
          返回
        </button>
        <div>
          <h1 className="text-2xl font-bold text-white">我的模板</h1>
          <p className="text-sm text-slate-500 mt-1">管理已保存的开场白和片尾模板</p>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-end mb-6">
        <button
          onClick={() => setPage("workshop")}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 text-slate-300 rounded-lg text-xs transition-all"
        >
          <ExternalLink size={12} />
          播客工坊
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-brand-pink" />
        </div>
      ) : (
        <div className="space-y-8">
          {/* Intro presets */}
          <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-pink" />
              开场白模板
            </h2>
            {renderPresetList("intro", introPresets)}
          </div>

          {/* Outro presets */}
          <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-tertiary" />
              片尾模板
            </h2>
            {renderPresetList("outro", outroPresets)}
          </div>
        </div>
      )}
    </div>
  );
}