import { useState, useEffect, useRef } from "react";
import {
  Mic,
  Music,
  Type,
  Save,
  Plus,
  Trash2,
  Upload,
  Check,
  Loader2,
  ArrowLeft,
  Play,
  Pause,
  ExternalLink,
} from "lucide-react";
import { useAppStore } from "../store";
import { getBGMs, uploadBGM, deleteBGM, generateIntroPresets, generateOutroPresets, saveSettingsPresets, generateTTS } from "../api";

const BGM_STYLES = [
  { id: "warm", label: "暖室", desc: "温暖大调和弦" },
  { id: "cool", label: "静夜", desc: "冷静小调氛围" },
  { id: "micro", label: "微光", desc: "现代电子感" },
  { id: "minimal", label: "留白", desc: "极简房间音" },
];

const OUTRO_MODES = [
  { id: "template", label: "固定结束语" },
  { id: "ai_summary", label: "AI 本期总结" },
  { id: "none", label: "无片尾" },
];

const SPEAKERS = [
  { id: "主持", label: "主持" },
  { id: "嘉宾", label: "嘉宾" },
  { id: "双声", label: "双声" },
];

export default function WorkshopPage() {
  const setPage = useAppStore((s) => s.setPage);
  const podcastSettings = useAppStore((s) => s.podcastSettings);
  const setPodcastSettings = useAppStore((s) => s.setPodcastSettings);
  const showToast = useAppStore((s) => s.showToast);

  const [localSettings, setLocalSettings] = useState(() => ({
    intro: {
      enabled: true,
      template: "欢迎收听播刻。今天我们要聊的是——{topic}。",
      speaker: "主持",
      voice_id: null,
      transition_style: "warm",
      transition_duration: 3.0,
      transition_volume: 0.15,
    },
    outro: {
      enabled: true,
      mode: "template",
      template: "以上就是本期节目的全部内容。感谢收听播刻，我们下期再见。",
      speaker: "主持",
      voice_id: null,
    },
    body_bgm: {
      enabled: false,
      style: "minimal",
      volume: 0.08,
      custom_path: null,
      source: "generated",
    },
    intro_presets: [],
    outro_presets: [],
    ...(podcastSettings || {}),
  }));

  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [bgmFiles, setBgmFiles] = useState([]);
  const [uploadingBgm, setUploadingBgm] = useState(false);

  // AI generation state
  const [aiGeneratingIntro, setAiGeneratingIntro] = useState(false);
  const [aiGeneratedIntroPresets, setAiGeneratedIntroPresets] = useState([]);
  const [aiGeneratingOutro, setAiGeneratingOutro] = useState(false);
  const [aiGeneratedOutroPresets, setAiGeneratedOutroPresets] = useState([]);

  // TTS preview state
  const [previewingId, setPreviewingId] = useState(null);
  const [playingId, setPlayingId] = useState(null);
  const audioRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const [settingsResp, bgmResp] = await Promise.all([
          fetch("/api/settings").then((r) => (r.ok ? r.json() : null)),
          getBGMs().catch(() => ({ files: [] })),
        ]);
        if (settingsResp) {
          const merged = {
            ...localSettings,
            ...settingsResp,
            body_bgm: {
              ...localSettings.body_bgm,
              ...settingsResp.body_bgm,
              source: settingsResp.body_bgm?.custom_path ? "uploaded" : "generated",
            },
          };
          setLocalSettings(merged);
          setPodcastSettings(merged);
        }
        if (bgmResp?.files) setBgmFiles(bgmResp.files);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {
        ...localSettings,
        body_bgm: { ...localSettings.body_bgm, source: undefined },
      };
      const resp = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      setPodcastSettings(data);
      showToast("包装设置已保存", "success");
    } catch {
      showToast("保存失败", "error");
    } finally {
      setSaving(false);
    }
  };

  const updateIntro = (key, value) =>
    setLocalSettings((prev) => ({ ...prev, intro: { ...prev.intro, [key]: value } }));
  const updateOutro = (key, value) =>
    setLocalSettings((prev) => ({ ...prev, outro: { ...prev.outro, [key]: value } }));
  const updateBodyBgm = (key, value) =>
    setLocalSettings((prev) => ({ ...prev, body_bgm: { ...prev.body_bgm, [key]: value } }));

  // ── AI generation ──────────────────────────────────────────────────

  const handleGenerateIntroPresets = async () => {
    setAiGeneratingIntro(true);
    setAiGeneratedIntroPresets([]);
    try {
      const result = await generateIntroPresets({ topic: "今日话题", count: 3 });
      setAiGeneratedIntroPresets(result.presets || []);
    } catch (e) {
      showToast("AI 生成失败：" + e.message, "error");
    } finally {
      setAiGeneratingIntro(false);
    }
  };

  const handleGenerateOutroPresets = async () => {
    setAiGeneratingOutro(true);
    setAiGeneratedOutroPresets([]);
    try {
      const result = await generateOutroPresets({ topic: "今日话题", count: 3 });
      setAiGeneratedOutroPresets(result.presets || []);
    } catch (e) {
      showToast("AI 生成失败：" + e.message, "error");
    } finally {
      setAiGeneratingOutro(false);
    }
  };

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

  // ── Save presets ────────────────────────────────────────────────────

  const handleSaveAiPresets = async (section, presets) => {
    const presetsKey = `${section}_presets`;
    try {
      await saveSettingsPresets({ [presetsKey]: presets });
      setLocalSettings((prev) => ({
        ...prev,
        [presetsKey]: [...(prev[presetsKey] || []), ...presets],
      }));
      if (section === "intro") setAiGeneratedIntroPresets([]);
      else setAiGeneratedOutroPresets([]);
      showToast("已保存到模板库", "success");
    } catch (e) {
      showToast("保存失败：" + e.message, "error");
    }
  };

  // ── BGM ─────────────────────────────────────────────────────────────

  const handleBgmUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingBgm(true);
    try {
      const result = await uploadBGM(file);
      setBgmFiles((prev) => [...prev, { id: result.saved_name, name: result.filename, size: file.size }]);
      showToast("背景音乐上传成功", "success");
    } catch (err) {
      showToast(err.message || "上传失败", "error");
    } finally {
      setUploadingBgm(false);
      if (e.target) e.target.value = "";
    }
  };

  const handleDeleteBgm = async (fileId) => {
    try {
      await deleteBGM(fileId);
      setBgmFiles((prev) => prev.filter((f) => f.id !== fileId));
      if (localSettings.body_bgm.custom_path === fileId) updateBodyBgm("custom_path", null);
      showToast("已删除", "success");
    } catch {
      showToast("删除失败", "error");
    }
  };

  // ── Render ──────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 size={24} className="animate-spin text-brand-pink" />
      </div>
    );
  }

  return (
    <div className="p-10 max-w-2xl mx-auto">
      {/* Hidden audio element for TTS preview */}
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
          <h1 className="text-2xl font-bold text-white">播客工坊</h1>
          <p className="text-sm text-slate-500 mt-1">生成并试听开场白 / 片尾，管理包装设置</p>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage("myTemplates")}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 text-slate-300 rounded-lg text-xs transition-all"
          >
            <ExternalLink size={12} />
            我的模板
          </button>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-pink/10 hover:bg-brand-pink/20 text-brand-pink rounded-lg text-xs font-medium transition-all disabled:opacity-50"
        >
          <Save size={12} />
          {saving ? "保存中..." : "保存设置"}
        </button>
      </div>

      <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5 space-y-8">
        {/* ══════ INTRO ══════ */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Mic size={14} className="text-brand-tertiary" />
              <span className="text-sm font-medium text-white">开场白</span>
            </div>
            <button
              onClick={() => updateIntro("enabled", !localSettings.intro.enabled)}
              className={`w-9 h-5 rounded-full relative cursor-pointer flex-shrink-0 transition-colors ${
                localSettings.intro.enabled ? "bg-brand-pink" : "bg-white/10"
              }`}
            >
              <div
                className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${
                  localSettings.intro.enabled ? "right-0.5" : "left-0.5"
                }`}
              />
            </button>
          </div>

          {localSettings.intro.enabled && (
            <div className="space-y-4 pl-6 border-l border-[#2a2a2a]">
              {/* Current template */}
              <div>
                <label className="text-[10px] text-slate-500 mb-1 block">文案（支持 {"{topic}"} 占位符）</label>
                <textarea
                  value={localSettings.intro.template}
                  onChange={(e) => updateIntro("template", e.target.value)}
                  rows={2}
                  className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg p-2.5 text-xs text-white placeholder-slate-600 resize-none outline-none focus:border-brand-pink/30"
                />
              </div>

              {/* Speaker & Transition */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">说话人</label>
                  <div className="flex gap-2">
                    {SPEAKERS.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => updateIntro("speaker", s.id)}
                        className={`flex-1 py-1.5 rounded-lg text-xs transition-all ${
                          localSettings.intro.speaker === s.id
                            ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                            : "bg-white/5 text-slate-400 border border-transparent hover:bg-white/10"
                        }`}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">过渡音乐风格</label>
                  <select
                    value={localSettings.intro.transition_style}
                    onChange={(e) => updateIntro("transition_style", e.target.value)}
                    className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg py-1.5 px-2 text-xs text-white outline-none focus:border-brand-pink/30"
                  >
                    {BGM_STYLES.map((s) => (
                      <option key={s.id} value={s.id}>{s.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Transition duration & volume */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">过渡时长: {localSettings.intro.transition_duration.toFixed(1)}s</label>
                  <input
                    type="range"
                    min={1} max={8} step={0.5}
                    value={localSettings.intro.transition_duration}
                    onChange={(e) => updateIntro("transition_duration", parseFloat(e.target.value))}
                    className="w-full accent-brand-pink"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">过渡音量: {Math.round(localSettings.intro.transition_volume * 100)}%</label>
                  <input
                    type="range"
                    min={0.05} max={0.3} step={0.01}
                    value={localSettings.intro.transition_volume}
                    onChange={(e) => updateIntro("transition_volume", parseFloat(e.target.value))}
                    className="w-full accent-brand-pink"
                  />
                </div>
              </div>

              {/* AI generation */}
              <div className="pt-2 border-t border-[#2a2a2a]">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[10px] text-slate-500 font-medium">AI 批量生成开场白</span>
                  <button
                    onClick={handleGenerateIntroPresets}
                    disabled={aiGeneratingIntro}
                    className="flex items-center gap-1 text-xs text-brand-tertiary hover:text-brand-tertiary/80 transition-colors disabled:opacity-50"
                  >
                    {aiGeneratingIntro ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                    {aiGeneratingIntro ? "生成中..." : "生成"}
                  </button>
                </div>

                {aiGeneratedIntroPresets.length > 0 && (
                  <div className="space-y-2">
                    {aiGeneratedIntroPresets.map((preset, i) => {
                      const previewKey = `intro_${preset.id || preset.name}`;
                      return (
                        <div key={i} className="flex items-start gap-2 bg-[#1a1a1c] border border-brand-pink/10 rounded-lg p-3">
                          <div className="flex-1 min-w-0">
                            <div className="text-xs text-white font-medium mb-0.5">{preset.name}</div>
                            <div className="text-[11px] text-slate-400 truncate">{preset.template}</div>
                          </div>
                          <div className="flex items-center gap-1 flex-shrink-0">
                            <button
                              onClick={() => handlePreview("intro", preset)}
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
                              onClick={() => handleSaveAiPresets("intro", [preset])}
                              className="px-2 py-1 rounded text-[10px] bg-brand-pink/10 text-brand-pink hover:bg-brand-pink/20 transition-colors"
                            >
                              保存
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* ══════ OUTRO ══════ */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Type size={14} className="text-brand-tertiary" />
              <span className="text-sm font-medium text-white">片尾</span>
            </div>
            <button
              onClick={() => updateOutro("enabled", !localSettings.outro.enabled)}
              className={`w-9 h-5 rounded-full relative cursor-pointer flex-shrink-0 transition-colors ${
                localSettings.outro.enabled ? "bg-brand-pink" : "bg-white/10"
              }`}
            >
              <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${localSettings.outro.enabled ? "right-0.5" : "left-0.5"}`} />
            </button>
          </div>

          {localSettings.outro.enabled && (
            <div className="space-y-4 pl-6 border-l border-[#2a2a2a]">
              <div className="flex gap-2">
                {OUTRO_MODES.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => updateOutro("mode", m.id)}
                    className={`flex-1 py-1.5 rounded-lg text-xs transition-all ${
                      localSettings.outro.mode === m.id
                        ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                        : "bg-white/5 text-slate-400 border border-transparent hover:bg-white/10"
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>

              {localSettings.outro.mode === "template" && (
                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">片尾结束语</label>
                  <textarea
                    value={localSettings.outro.template}
                    onChange={(e) => updateOutro("template", e.target.value)}
                    rows={2}
                    className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg p-2.5 text-xs text-white placeholder-slate-600 resize-none outline-none focus:border-brand-pink/30"
                  />
                </div>
              )}

              <div>
                <label className="text-[10px] text-slate-500 mb-1 block">说话人</label>
                <div className="flex gap-2">
                  {SPEAKERS.slice(0, 2).map((s) => (
                    <button
                      key={s.id}
                      onClick={() => updateOutro("speaker", s.id)}
                      className={`flex-1 py-1.5 rounded-lg text-xs transition-all ${
                        localSettings.outro.speaker === s.id
                          ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                          : "bg-white/5 text-slate-400 border border-transparent hover:bg-white/10"
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* AI generation */}
              <div className="pt-2 border-t border-[#2a2a2a]">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[10px] text-slate-500 font-medium">AI 批量生成片尾</span>
                  <button
                    onClick={handleGenerateOutroPresets}
                    disabled={aiGeneratingOutro}
                    className="flex items-center gap-1 text-xs text-brand-tertiary hover:text-brand-tertiary/80 transition-colors disabled:opacity-50"
                  >
                    {aiGeneratingOutro ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                    {aiGeneratingOutro ? "生成中..." : "生成"}
                  </button>
                </div>

                {aiGeneratedOutroPresets.length > 0 && (
                  <div className="space-y-2">
                    {aiGeneratedOutroPresets.map((preset, i) => {
                      const previewKey = `outro_${preset.id || preset.name}`;
                      return (
                        <div key={i} className="flex items-start gap-2 bg-[#1a1a1c] border border-brand-pink/10 rounded-lg p-3">
                          <div className="flex-1 min-w-0">
                            <div className="text-xs text-white font-medium mb-0.5">{preset.name}</div>
                            <div className="text-[11px] text-slate-400 truncate">{preset.template}</div>
                          </div>
                          <div className="flex items-center gap-1 flex-shrink-0">
                            <button
                              onClick={() => handlePreview("outro", preset)}
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
                              onClick={() => handleSaveAiPresets("outro", [preset])}
                              className="px-2 py-1 rounded text-[10px] bg-brand-pink/10 text-brand-pink hover:bg-brand-pink/20 transition-colors"
                            >
                              保存
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* ══════ BODY BGM ══════ */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Music size={14} className="text-brand-tertiary" />
              <span className="text-sm font-medium text-white">正文背景音乐</span>
            </div>
            <button
              onClick={() => updateBodyBgm("enabled", !localSettings.body_bgm.enabled)}
              className={`w-9 h-5 rounded-full relative cursor-pointer flex-shrink-0 transition-colors ${
                localSettings.body_bgm.enabled ? "bg-brand-pink" : "bg-white/10"
              }`}
            >
              <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${localSettings.body_bgm.enabled ? "right-0.5" : "left-0.5"}`} />
            </button>
          </div>

          {localSettings.body_bgm.enabled && (
            <div className="pl-6 border-l border-[#2a2a2a] space-y-4">
              <div>
                <label className="text-[10px] text-slate-500 mb-1 block">来源</label>
                <div className="flex gap-2">
                  <button
                    onClick={() => updateBodyBgm("source", "generated")}
                    className={`flex-1 py-1.5 rounded-lg text-xs transition-all ${
                      localSettings.body_bgm.source !== "uploaded"
                        ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                        : "bg-white/5 text-slate-400 border border-transparent hover:bg-white/10"
                    }`}
                  >
                    程序生成
                  </button>
                  <button
                    onClick={() => updateBodyBgm("source", "uploaded")}
                    className={`flex-1 py-1.5 rounded-lg text-xs transition-all ${
                      localSettings.body_bgm.source === "uploaded"
                        ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                        : "bg-white/5 text-slate-400 border border-transparent hover:bg-white/10"
                    }`}
                  >
                    自定义上传
                  </button>
                </div>
              </div>

              {localSettings.body_bgm.source !== "uploaded" ? (
                <>
                  <div>
                    <label className="text-[10px] text-slate-500 mb-1 block">默认风格</label>
                    <select
                      value={localSettings.body_bgm.style}
                      onChange={(e) => updateBodyBgm("style", e.target.value)}
                      className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg py-1.5 px-2 text-xs text-white outline-none focus:border-brand-pink/30"
                    >
                      {BGM_STYLES.map((s) => (
                        <option key={s.id} value={s.id}>{s.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 mb-1 block">默认音量: {Math.round(localSettings.body_bgm.volume * 100)}%</label>
                    <input
                      type="range" min={0.02} max={0.2} step={0.01}
                      value={localSettings.body_bgm.volume}
                      onChange={(e) => updateBodyBgm("volume", parseFloat(e.target.value))}
                      className="w-full accent-brand-pink"
                    />
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label className="text-[10px] text-slate-500 mb-1 block">选择已上传的背景音乐</label>
                    {bgmFiles.length === 0 ? (
                      <div className="text-xs text-slate-500 bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg p-3">
                        暂无上传的背景音乐
                      </div>
                    ) : (
                      <div className="space-y-1.5">
                        {bgmFiles.map((f) => (
                          <div key={f.id} className={`flex items-center justify-between bg-[#1a1a1c] border rounded-lg px-3 py-2 ${
                            localSettings.body_bgm.custom_path === f.id ? "border-brand-pink/30" : "border-[#2a2a2a]"
                          }`}>
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              <Music size={12} className="text-slate-500" />
                              <span className="text-xs text-white truncate">{f.name}</span>
                            </div>
                            <div className="flex items-center gap-1.5 ml-2">
                              <button
                                onClick={() => updateBodyBgm("custom_path", f.id)}
                                className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                                  localSettings.body_bgm.custom_path === f.id
                                    ? "bg-brand-pink/10 text-brand-pink"
                                    : "bg-white/5 text-slate-400 hover:bg-white/10 hover:text-white"
                                }`}
                              >
                                {localSettings.body_bgm.custom_path === f.id ? "已选" : "选用"}
                              </button>
                              <button onClick={() => handleDeleteBgm(f.id)} className="p-1 rounded hover:bg-red-500/10 text-slate-400 hover:text-red-400 transition-colors">
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <div>
                    <input type="file" accept=".mp3,.wav,.m4a,.ogg" onChange={handleBgmUpload} className="hidden" id="bgm-upload" />
                    <button
                      onClick={() => document.getElementById("bgm-upload")?.click()}
                      disabled={uploadingBgm}
                      className="flex items-center gap-1.5 w-full justify-center py-2 rounded-lg bg-white/5 hover:bg-white/10 text-xs text-slate-300 transition-all disabled:opacity-50 border border-dashed border-[#2a2a2a]"
                    >
                      {uploadingBgm ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
                      {uploadingBgm ? "上传中..." : "上传背景音乐"}
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}