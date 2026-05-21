import { useState, useEffect, useRef } from "react";
import {
  ArrowLeft,
  Play,
  Plus,
  Trash2,
  MessageSquare,
  Clock,
  Loader2,
  AlertCircle,
  FileText,
  List,
  Mic,
  ChevronDown,
  Music,
  Volume2,
  Save,
  SlidersHorizontal,
} from "lucide-react";
import { useAppStore } from "../store";
import { generateTTS, getBGMs, reportUserAction } from "../api";

export default function ScriptEditorPage() {
  const setPage = useAppStore((s) => s.setPage);
  const scriptData = useAppStore((s) => s.scriptData);
  const setScriptData = useAppStore((s) => s.setScriptData);
  const showToast = useAppStore((s) => s.showToast);
  const maleVoiceId = useAppStore((s) => s.maleVoiceId);
  const setMaleVoiceId = useAppStore((s) => s.setMaleVoiceId);
  const femaleVoiceId = useAppStore((s) => s.femaleVoiceId);
  const setFemaleVoiceId = useAppStore((s) => s.setFemaleVoiceId);
  const defaultEmotion = useAppStore((s) => s.defaultEmotion);
  const podcastSettings = useAppStore((s) => s.podcastSettings);
  const [loading, setLoading] = useState(false);
  const [rawMode, setRawMode] = useState(false);
  const [rawText, setRawText] = useState("");

  // Voice dropdown state
  const [fetchedVoices, setFetchedVoices] = useState([]);
  const [openDropdown, setOpenDropdown] = useState(null);
  const dropdownRef = useRef(null);

  // BGM files
  const [bgmFiles, setBgmFiles] = useState([]);

  // Episode audio arrangement overrides
  const [activeTab, setActiveTab] = useState("script");
  const [useCustomAudio, setUseCustomAudio] = useState(false);
  const global = podcastSettings || {};
  const [episodeAudio, setEpisodeAudio] = useState(() => ({
    intro: {
      enabled: global.intro?.enabled !== false,
      preset_id: null,
    },
    outro: {
      enabled: global.outro?.enabled !== false,
      mode: global.outro?.mode || "template",
      preset_id: null,
    },
    body_bgm: {
      enabled: global.body_bgm?.enabled || false,
      style: global.body_bgm?.style || "minimal",
      volume: global.body_bgm?.volume ?? 0.08,
      source: global.body_bgm?.custom_path ? "uploaded" : "generated",
      custom_path: global.body_bgm?.custom_path || null,
    },
  }));

  const BGM_STYLES = [
    { id: "warm", label: "暖室" },
    { id: "cool", label: "静夜" },
    { id: "micro", label: "微光" },
    { id: "minimal", label: "留白" },
  ];

  const OUTRO_MODES = [
    { id: "template", label: "固定结束语" },
    { id: "ai_summary", label: "AI 本期总结" },
    { id: "none", label: "无片尾" },
  ];

  const BUILT_IN_MALE = [
    { id: "639cdf5253a24b50a18cbdb726acce15", name: "默认主持" },
  ];
  const BUILT_IN_FEMALE = [
    { id: "a71b052094fa4505967e262b8cb7d0a6", name: "默认嘉宾" },
  ];

  useEffect(() => {
    fetch("/api/voices")
      .then((r) => r.json())
      .then((data) => {
        if (data.voices) setFetchedVoices(data.voices);
      })
      .catch(() => {});
    getBGMs()
      .then((data) => {
        if (data.files) setBgmFiles(data.files);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpenDropdown(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Local editable copy
  const [script, setScript] = useState(() => {
    if (scriptData && scriptData.length > 0) return scriptData;
    try {
      const saved = localStorage.getItem("boke_draft_script");
      if (saved) return JSON.parse(saved);
    } catch {}
    return [];
  });

  // Auto-save draft to localStorage
  useEffect(() => {
    if (script && script.length > 0) {
      localStorage.setItem("boke_draft_script", JSON.stringify(script));
    }
  }, [script]);

  // When a new script is generated, replace draft and clear storage
  useEffect(() => {
    if (scriptData && scriptData.length > 0) {
      setScript(scriptData);
      localStorage.removeItem("boke_draft_script");
    }
  }, [scriptData]);

  const updateTurn = (index, field, value) => {
    const next = [...script];
    next[index] = { ...next[index], [field]: value };
    setScript(next);
  };

  const deleteTurn = (index) => {
    const next = script.filter((_, i) => i !== index);
    setScript(next);
  };

  const addTurn = (index) => {
    const speaker =
      script[index]?.speaker === "主持" ? "嘉宾" : "主持";
    const next = [...script];
    next.splice(index + 1, 0, { speaker, text: "", emotion: defaultEmotion });
    setScript(next);
  };

  const swapSpeaker = (index) => {
    const current = script[index]?.speaker;
    const nextSpeaker = current === "主持" ? "嘉宾" : "主持";
    updateTurn(index, "speaker", nextSpeaker);
  };

  const handleGeneratePodcast = async () => {
    const validScript = script.filter((t) => t.text?.trim());
    if (validScript.length < 3) {
      showToast("对话内容太少，至少需要 3 轮对话", "error");
      return;
    }

    setLoading(true);
    try {
      // Report edit_generate action
      const sessionId = useAppStore.getState().sessionId;
      reportUserAction({
        session_id: sessionId,
        action_type: "edit_generate",
      });
      // Persist edited script
      setScriptData(validScript);
      const voiceMap = { 主持: maleVoiceId, 嘉宾: femaleVoiceId };
      const payload = { script: validScript, voice_map: voiceMap };
      if (useCustomAudio) {
        const arrangement = {
          intro: {
            enabled: episodeAudio.intro.enabled,
            ...(episodeAudio.intro.preset_id
              ? { intro_preset_id: episodeAudio.intro.preset_id }
              : {}),
          },
          outro: {
            enabled: episodeAudio.outro.enabled,
            mode: episodeAudio.outro.mode,
            ...(episodeAudio.outro.preset_id
              ? { outro_preset_id: episodeAudio.outro.preset_id }
              : {}),
          },
          body_bgm: {
            enabled: episodeAudio.body_bgm.enabled,
            style: episodeAudio.body_bgm.style,
            volume: episodeAudio.body_bgm.volume,
            custom_path:
              episodeAudio.body_bgm.source === "uploaded"
                ? episodeAudio.body_bgm.custom_path
                : null,
          },
        };
        payload.arrangement = arrangement;
      }
      const { blob } = await generateTTS(payload);
      const url = URL.createObjectURL(blob);
      useAppStore.getState().setFullAudioUrl(url);
      setPage("player");
      showToast("播客生成成功！", "success");
    } catch (e) {
      showToast(e.message || "语音合成失败", "error");
    } finally {
      setLoading(false);
    }
  };

  const yangCount = script.filter((t) => t.speaker === "主持").length;
  const jiangCount = script.filter((t) => t.speaker === "嘉宾").length;
  const totalChars = script.reduce((sum, t) => sum + (t.text?.length || 0), 0);
  const estMinutes = Math.max(1, Math.round(totalChars / 280));

  if (!scriptData || script.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-10">
        <AlertCircle size={48} className="text-slate-600 mb-4" />
        <p className="text-slate-500 mb-6">还没有生成文稿，请返回首页上传内容。</p>
        <button
          onClick={() => setPage("home")}
          className="flex items-center gap-2 px-6 py-3 bg-white text-black rounded-xl text-sm font-bold hover:bg-white/90 transition-all"
        >
          <ArrowLeft size={16} />
          返回首页
        </button>
      </div>
    );
  }

  const introPresets = podcastSettings?.intro_presets || [];
  const outroPresets = podcastSettings?.outro_presets || [];

  return (
    <div className="p-10 max-w-3xl mx-auto">
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
            <h1 className="text-xl font-bold text-white">文稿编辑</h1>
            <p className="text-xs text-slate-500 mt-1">
              修改对话内容，确认后生成播客 · 预估时长 <span className="text-brand-pink font-bold">{estMinutes}</span> 分钟
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              if (!rawMode) {
                setRawText(script.map((t) => `${t.speaker === "主持" ? "主持" : "嘉宾"}：${t.text}`).join("\n"));
              } else {
                // Parse raw text back to script
                const lines = rawText.split("\n").filter((l) => l.trim());
                const parsed = [];
                const pattern = /^(主持|嘉宾)[：:]\s*(.+)/;
                const speakerMap = { 主持: "主持", 嘉宾: "嘉宾" };
                for (const line of lines) {
                  const m = line.match(pattern);
                  if (m) parsed.push({ speaker: speakerMap[m[1]], text: m[2].trim() });
                }
                if (parsed.length > 0) setScript(parsed);
              }
              setRawMode(!rawMode);
            }}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
              rawMode
                ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                : "bg-white/5 text-slate-400 hover:text-white border border-transparent"
            }`}
          >
            {rawMode ? <List size={16} /> : <FileText size={16} />}
            <span>{rawMode ? "卡片模式" : "文本模式"}</span>
          </button>
          <button
            onClick={() => {
              setActiveTab("audio");
              setUseCustomAudio(true);
            }}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all bg-white/5 text-slate-400 hover:text-white border border-transparent"
          >
            <SlidersHorizontal size={16} />
            <span>音频设置</span>
          </button>
          <button
            onClick={handleGeneratePodcast}
            disabled={loading}
            className="flex items-center gap-2 px-6 py-3 bg-brand-pink hover:bg-brand-pink/80 disabled:bg-brand-pink/40 text-white rounded-xl text-sm font-bold transition-all"
          >
            {loading ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Play size={16} />
            )}
            <span>{loading ? "生成中..." : "生成播客"}</span>
          </button>
        </div>
      </div>

      {/* Stats bar */}
      <div className="flex items-center gap-6 mb-4 text-xs text-slate-500">
        <span className="flex items-center gap-1.5">
          <MessageSquare size={14} />
          {script.length} 轮对话
        </span>
        <span className="text-slate-600">主持 {yangCount} 轮 · 嘉宾 {jiangCount} 轮</span>
        <span className="text-slate-600">{totalChars} 字</span>
      </div>

      {/* Voice config bar */}
      <div ref={dropdownRef} className="flex items-center gap-4 mb-6">
        {/* Male voice selector */}
        <div className="relative">
          <button
            onClick={() => setOpenDropdown(openDropdown === "male" ? null : "male")}
            className="flex items-center gap-2 px-3 py-1.5 bg-white/5 border border-[#2a2a2a] hover:border-white/20 rounded-lg text-xs text-white transition-all"
          >
            <Mic size={12} className="text-brand-pink" />
            <span>
              主持：
              {[...BUILT_IN_MALE, ...fetchedVoices].find((v) => v.id === maleVoiceId)?.title ||
               [...BUILT_IN_MALE, ...fetchedVoices].find((v) => v.id === maleVoiceId)?.name ||
               "默认"}
            </span>
            <ChevronDown size={12} className={`text-slate-500 transition-transform ${openDropdown === "male" ? "rotate-180" : ""}`} />
          </button>
          {openDropdown === "male" && (
            <div className="absolute z-20 mt-1 w-48 bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg shadow-xl overflow-hidden max-h-48 overflow-y-auto">
              {[...BUILT_IN_MALE, ...fetchedVoices].map((v) => (
                <div
                  key={v.id}
                  onClick={() => { setMaleVoiceId(v.id); setOpenDropdown(null); }}
                  className="px-3 py-2 hover:bg-white/5 cursor-pointer transition-colors text-xs text-white"
                >
                  {v.title || v.name}
                </div>
              ))}
              <button
                onClick={() => { setOpenDropdown(null); setPage("myVoices"); }}
                className="w-full flex items-center gap-1.5 px-3 py-2 text-[10px] text-brand-pink hover:bg-brand-pink/10 transition-colors border-t border-[#2a2a2a]"
              >
                <Plus size={10} /> 添加音色
              </button>
            </div>
          )}
        </div>

        {/* Female voice selector */}
        <div className="relative">
          <button
            onClick={() => setOpenDropdown(openDropdown === "female" ? null : "female")}
            className="flex items-center gap-2 px-3 py-1.5 bg-white/5 border border-[#2a2a2a] hover:border-white/20 rounded-lg text-xs text-white transition-all"
          >
            <Mic size={12} className="text-brand-tertiary" />
            <span>
              嘉宾：
              {[...BUILT_IN_FEMALE, ...fetchedVoices].find((v) => v.id === femaleVoiceId)?.title ||
               [...BUILT_IN_FEMALE, ...fetchedVoices].find((v) => v.id === femaleVoiceId)?.name ||
               "默认"}
            </span>
            <ChevronDown size={12} className={`text-slate-500 transition-transform ${openDropdown === "female" ? "rotate-180" : ""}`} />
          </button>
          {openDropdown === "female" && (
            <div className="absolute z-20 mt-1 w-48 bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg shadow-xl overflow-hidden max-h-48 overflow-y-auto">
              {[...BUILT_IN_FEMALE, ...fetchedVoices].map((v) => (
                <div
                  key={v.id}
                  onClick={() => { setFemaleVoiceId(v.id); setOpenDropdown(null); }}
                  className="px-3 py-2 hover:bg-white/5 cursor-pointer transition-colors text-xs text-white"
                >
                  {v.title || v.name}
                </div>
              ))}
              <button
                onClick={() => { setOpenDropdown(null); setPage("myVoices"); }}
                className="w-full flex items-center gap-1.5 px-3 py-2 text-[10px] text-brand-pink hover:bg-brand-pink/10 transition-colors border-t border-[#2a2a2a]"
              >
                <Plus size={10} /> 添加音色
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 mb-4 border-b border-[#2a2a2a]">
        <button
          onClick={() => setActiveTab("script")}
          className={`px-4 py-2 text-xs font-medium transition-all border-b-2 ${
            activeTab === "script"
              ? "text-brand-pink border-brand-pink"
              : "text-slate-500 border-transparent hover:text-white"
          }`}
        >
          文稿
        </button>
        <button
          onClick={() => setActiveTab("audio")}
          className={`px-4 py-2 text-xs font-medium transition-all border-b-2 ${
            activeTab === "audio"
              ? "text-brand-pink border-brand-pink"
              : "text-slate-500 border-transparent hover:text-white"
          }`}
        >
          音频编排
        </button>
      </div>

      {/* Script Tab */}
      {activeTab === "script" && (
        <>
      {/* Raw text mode */}
      {rawMode ? (
        <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl overflow-hidden">
          <div className="px-4 py-3 border-b border-[#2a2a2a] flex items-center justify-between">
            <span className="text-xs text-slate-500">每行格式：主持：... 或 嘉宾：...</span>
            <span className="text-xs text-slate-600">{rawText.length} 字符</span>
          </div>
          <textarea
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            className="w-full h-[60vh] bg-[#1a1a1c] p-4 text-sm text-white placeholder-slate-600 resize-none outline-none leading-relaxed font-mono"
            placeholder="主持：...&#10;嘉宾：..."
          />
        </div>
      ) : (
        <div className="space-y-3">
          {script.map((turn, index) => (
            <div
              key={index}
              className="bg-[#161618] border border-[#2a2a2a] rounded-2xl overflow-hidden group hover:border-white/10 transition-all"
            >
              <div className="flex items-start gap-3 p-4">
                {/* Speaker + Emotion */}
                <div className="flex flex-col items-center gap-1.5 flex-shrink-0">
                  <button
                    onClick={() => swapSpeaker(index)}
                    className={`w-12 h-12 rounded-xl flex items-center justify-center text-xs font-bold transition-all ${
                      turn.speaker === "主持"
                        ? "bg-brand-pink/10 text-brand-pink hover:bg-brand-pink/20"
                        : "bg-brand-tertiary/10 text-brand-tertiary hover:bg-brand-tertiary/20"
                    }`}
                    title="点击切换发言人"
                  >
                    {turn.speaker === "主持" ? "主持" : "嘉宾"}
                  </button>
                  <input
                    value={turn.emotion || ""}
                    onChange={(e) => updateTurn(index, "emotion", e.target.value)}
                    placeholder="正常"
                    title="情绪标签（如：兴奋/磁性/放慢/悲伤，或自由形式如 [speaking softly]）"
                    className="w-12 text-center bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg py-1 px-0.5 text-[10px] text-slate-400 placeholder-slate-600 outline-none focus:border-brand-pink/30 transition-all"
                  />
                </div>

                {/* Text area */}
                <div className="flex-1">
                  <textarea
                    value={turn.text || ""}
                    onChange={(e) => updateTurn(index, "text", e.target.value)}
                    className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg p-3 text-sm text-white placeholder-slate-600 resize-none outline-none focus:border-brand-pink/30 transition-all leading-relaxed"
                    rows={Math.max(2, Math.ceil((turn.text?.length || 0) / 40))}
                    placeholder={`${turn.speaker === "主持" ? "主持" : "嘉宾"}说...`}
                  />
                </div>

                {/* Actions */}
                <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => addTurn(index)}
                    className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-all"
                    title="下方插入一轮"
                  >
                    <Plus size={14} />
                  </button>
                  <button
                    onClick={() => deleteTurn(index)}
                    className="p-1.5 rounded-lg bg-white/5 hover:bg-red-500/10 text-slate-400 hover:text-red-400 transition-all"
                    title="删除"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add turn at end */}
      <button
        onClick={() =>
          setScript((prev) => [
            ...prev,
            {
              speaker: prev[prev.length - 1]?.speaker === "主持" ? "嘉宾" : "主持",
              text: "",
              emotion: defaultEmotion,
            },
          ])
        }
        className="w-full mt-4 py-3 rounded-2xl border border-dashed border-[#2a2a2a] text-slate-500 hover:text-white hover:border-white/20 transition-all text-sm flex items-center justify-center gap-2"
      >
        <Plus size={16} />
        添加一轮对话
      </button>
        </>
      )}

      {/* Audio Tab */}
      {activeTab === "audio" && (
        <div className="space-y-6">
          {/* Master override toggle */}
          <div className="flex items-center justify-between bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5">
            <div>
              <div className="text-sm font-medium text-white">本期自定义音频编排</div>
              <div className="text-xs text-slate-500 mt-0.5">
                关闭时将完全使用全局播客品牌设置
              </div>
            </div>
            <button
              onClick={() => setUseCustomAudio(!useCustomAudio)}
              className={`w-11 h-6 rounded-full relative cursor-pointer flex-shrink-0 transition-colors ${
                useCustomAudio ? "bg-brand-pink" : "bg-white/10"
              }`}
            >
              <div
                className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all ${
                  useCustomAudio ? "right-1" : "left-1"
                }`}
              />
            </button>
          </div>

          {/* Intro */}
          <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Mic size={14} className="text-brand-tertiary" />
                <span className="text-sm font-medium text-white">开场白</span>
              </div>
              <button
                onClick={() =>
                  setEpisodeAudio((prev) => ({
                    ...prev,
                    intro: { ...prev.intro, enabled: !prev.intro.enabled },
                  }))
                }
                disabled={!useCustomAudio}
                className={`w-9 h-5 rounded-full relative cursor-pointer flex-shrink-0 transition-colors ${
                  episodeAudio.intro.enabled ? "bg-brand-pink" : "bg-white/10"
                } disabled:opacity-40`}
              >
                <div
                  className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${
                    episodeAudio.intro.enabled ? "right-0.5" : "left-0.5"
                  }`}
                />
              </button>
            </div>

            {episodeAudio.intro.enabled && (
              <div className="pl-4 border-l border-[#2a2a2a] space-y-3">
                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">使用开场白模板（可选）</label>
                  <select
                    value={episodeAudio.intro.preset_id || ""}
                    disabled={!useCustomAudio}
                    onChange={(e) =>
                      setEpisodeAudio((prev) => ({
                        ...prev,
                        intro: { ...prev.intro, preset_id: e.target.value || null },
                      }))
                    }
                    className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg py-1.5 px-2 text-xs text-white outline-none focus:border-brand-pink/30 disabled:opacity-40"
                  >
                    <option value="">使用全局默认开场白</option>
                    {introPresets.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </div>

          {/* Body BGM */}
          <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Music size={14} className="text-brand-tertiary" />
                <span className="text-sm font-medium text-white">正文背景音乐</span>
              </div>
              <button
                onClick={() =>
                  setEpisodeAudio((prev) => ({
                    ...prev,
                    body_bgm: { ...prev.body_bgm, enabled: !prev.body_bgm.enabled },
                  }))
                }
                disabled={!useCustomAudio}
                className={`w-9 h-5 rounded-full relative cursor-pointer flex-shrink-0 transition-colors ${
                  episodeAudio.body_bgm.enabled ? "bg-brand-pink" : "bg-white/10"
                } disabled:opacity-40`}
              >
                <div
                  className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${
                    episodeAudio.body_bgm.enabled ? "right-0.5" : "left-0.5"
                  }`}
                />
              </button>
            </div>

            {episodeAudio.body_bgm.enabled && (
              <div className="space-y-3 pl-4 border-l border-[#2a2a2a]">
                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">来源</label>
                  <div className="flex gap-2">
                    <button
                      disabled={!useCustomAudio}
                      onClick={() =>
                        setEpisodeAudio((prev) => ({
                          ...prev,
                          body_bgm: { ...prev.body_bgm, source: "generated", custom_path: null },
                        }))
                      }
                      className={`flex-1 py-1.5 rounded-lg text-xs transition-all disabled:opacity-40 ${
                        episodeAudio.body_bgm.source !== "uploaded"
                          ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                          : "bg-white/5 text-slate-400 border border-transparent hover:bg-white/10"
                      }`}
                    >
                      程序生成
                    </button>
                    <button
                      disabled={!useCustomAudio}
                      onClick={() =>
                        setEpisodeAudio((prev) => ({
                          ...prev,
                          body_bgm: { ...prev.body_bgm, source: "uploaded" },
                        }))
                      }
                      className={`flex-1 py-1.5 rounded-lg text-xs transition-all disabled:opacity-40 ${
                        episodeAudio.body_bgm.source === "uploaded"
                          ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                          : "bg-white/5 text-slate-400 border border-transparent hover:bg-white/10"
                      }`}
                    >
                      自定义上传
                    </button>
                  </div>
                </div>

                {episodeAudio.body_bgm.source !== "uploaded" ? (
                  <>
                    <div>
                      <label className="text-[10px] text-slate-500 mb-1 block">风格</label>
                      <select
                        value={episodeAudio.body_bgm.style}
                        disabled={!useCustomAudio}
                        onChange={(e) =>
                          setEpisodeAudio((prev) => ({
                            ...prev,
                            body_bgm: { ...prev.body_bgm, style: e.target.value },
                          }))
                        }
                        className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg py-1.5 px-2 text-xs text-white outline-none focus:border-brand-pink/30 disabled:opacity-40"
                      >
                        {BGM_STYLES.map((s) => (
                          <option key={s.id} value={s.id}>{s.label}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="text-[10px] text-slate-500 mb-1 block">
                        音量: {Math.round(episodeAudio.body_bgm.volume * 100)}%
                      </label>
                      <input
                        type="range"
                        min={0.02}
                        max={0.2}
                        step={0.01}
                        disabled={!useCustomAudio}
                        value={episodeAudio.body_bgm.volume}
                        onChange={(e) =>
                          setEpisodeAudio((prev) => ({
                            ...prev,
                            body_bgm: { ...prev.body_bgm, volume: parseFloat(e.target.value) },
                          }))
                        }
                        className="w-full accent-brand-pink disabled:opacity-40"
                      />
                    </div>
                  </>
                ) : (
                  <div>
                    <label className="text-[10px] text-slate-500 mb-1 block">选择已上传的背景音乐</label>
                    {bgmFiles.length === 0 ? (
                      <div className="text-xs text-slate-500 bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg p-3">
                        暂无上传的背景音乐，请前往「设置 → 播客品牌 → 正文背景音乐」上传
                      </div>
                    ) : (
                      <div className="space-y-1.5">
                        {bgmFiles.map((f) => (
                          <div
                            key={f.id}
                            className={`flex items-center justify-between bg-[#1a1a1c] border rounded-lg px-3 py-2 ${
                              episodeAudio.body_bgm.custom_path === f.id
                                ? "border-brand-pink/30"
                                : "border-[#2a2a2a]"
                            }`}
                          >
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              <Music size={12} className="text-slate-500 flex-shrink-0" />
                              <span className="text-xs text-white truncate">{f.name}</span>
                            </div>
                            <button
                              disabled={!useCustomAudio}
                              onClick={() =>
                                setEpisodeAudio((prev) => ({
                                  ...prev,
                                  body_bgm: { ...prev.body_bgm, custom_path: f.id },
                                }))
                              }
                              className={`px-2 py-0.5 rounded text-[10px] transition-colors disabled:opacity-40 ${
                                episodeAudio.body_bgm.custom_path === f.id
                                  ? "bg-brand-pink/10 text-brand-pink"
                                  : "bg-white/5 text-slate-400 hover:bg-white/10 hover:text-white"
                              }`}
                            >
                              {episodeAudio.body_bgm.custom_path === f.id ? "已选" : "选用"}
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Outro */}
          <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <MessageSquare size={14} className="text-brand-tertiary" />
                <span className="text-sm font-medium text-white">片尾</span>
              </div>
              <button
                onClick={() =>
                  setEpisodeAudio((prev) => ({
                    ...prev,
                    outro: { ...prev.outro, enabled: !prev.outro.enabled },
                  }))
                }
                disabled={!useCustomAudio}
                className={`w-9 h-5 rounded-full relative cursor-pointer flex-shrink-0 transition-colors ${
                  episodeAudio.outro.enabled ? "bg-brand-pink" : "bg-white/10"
                } disabled:opacity-40`}
              >
                <div
                  className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${
                    episodeAudio.outro.enabled ? "right-0.5" : "left-0.5"
                  }`}
                />
              </button>
            </div>

            {episodeAudio.outro.enabled && (
              <div className="pl-4 border-l border-[#2a2a2a] space-y-3">
                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">模式</label>
                  <div className="flex gap-2">
                    {OUTRO_MODES.map((m) => (
                      <button
                        key={m.id}
                        disabled={!useCustomAudio}
                        onClick={() =>
                          setEpisodeAudio((prev) => ({
                            ...prev,
                            outro: { ...prev.outro, mode: m.id },
                          }))
                        }
                        className={`flex-1 py-1.5 rounded-lg text-xs transition-all disabled:opacity-40 ${
                          episodeAudio.outro.mode === m.id
                            ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                            : "bg-white/5 text-slate-400 border border-transparent hover:bg-white/10"
                        }`}
                      >
                        {m.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">使用片尾模板（可选）</label>
                  <select
                    value={episodeAudio.outro.preset_id || ""}
                    disabled={!useCustomAudio}
                    onChange={(e) =>
                      setEpisodeAudio((prev) => ({
                        ...prev,
                        outro: { ...prev.outro, preset_id: e.target.value || null },
                      }))
                    }
                    className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg py-1.5 px-2 text-xs text-white outline-none focus:border-brand-pink/30 disabled:opacity-40"
                  >
                    <option value="">使用全局默认片尾</option>
                    {outroPresets.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
