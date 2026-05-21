import { useState, useEffect } from "react";
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
} from "lucide-react";
import { useAppStore } from "../store";
import { getBGMs, uploadBGM, deleteBGM } from "../api";

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

function makeId() {
  return Math.random().toString(36).slice(2, 9);
}

export default function BrandPage() {
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
    intro_presets: [
      {
        id: "default",
        name: "默认开场白",
        template: "欢迎收听播刻。今天我们要聊的是——{topic}。",
        speaker: "主持",
        voice_id: null,
        transition_style: "warm",
        transition_duration: 3.0,
        transition_volume: 0.15,
      },
    ],
    outro_presets: [
      {
        id: "default",
        name: "默认片尾",
        mode: "template",
        template: "以上就是本期节目的全部内容。感谢收听播刻，我们下期再见。",
        speaker: "主持",
        voice_id: null,
      },
    ],
    ...(podcastSettings || {}),
  }));

  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [bgmFiles, setBgmFiles] = useState([]);
  const [uploadingBgm, setUploadingBgm] = useState(false);

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
        body_bgm: {
          ...localSettings.body_bgm,
          source: undefined,
        },
      };
      const resp = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      setPodcastSettings(data);
      showToast("节目包装设置已保存", "success");
    } catch (e) {
      showToast("保存失败", "error");
    } finally {
      setSaving(false);
    }
  };

  const updateIntro = (key, value) =>
    setLocalSettings((prev) => ({
      ...prev,
      intro: { ...prev.intro, [key]: value },
    }));

  const updateOutro = (key, value) =>
    setLocalSettings((prev) => ({
      ...prev,
      outro: { ...prev.outro, [key]: value },
    }));

  const updateBodyBgm = (key, value) =>
    setLocalSettings((prev) => ({
      ...prev,
      body_bgm: { ...prev.body_bgm, [key]: value },
    }));

  const addPreset = (section) => {
    const name = window.prompt(`请输入新${section === "intro" ? "开场白" : "片尾"}模板名称:`);
    if (!name || !name.trim()) return;
    const source = section === "intro" ? localSettings.intro : localSettings.outro;
    const newPreset = {
      id: makeId(),
      name: name.trim(),
      ...(section === "intro"
        ? {
            template: source.template,
            speaker: source.speaker,
            voice_id: source.voice_id,
            transition_style: source.transition_style,
            transition_duration: source.transition_duration,
            transition_volume: source.transition_volume,
          }
        : {
            mode: source.mode,
            template: source.template,
            speaker: source.speaker,
            voice_id: source.voice_id,
          }),
    };
    setLocalSettings((prev) => ({
      ...prev,
      [`${section}_presets`]: [...(prev[`${section}_presets`] || []), newPreset],
    }));
    showToast("模板已保存", "success");
  };

  const loadPreset = (section, preset) => {
    setLocalSettings((prev) => ({
      ...prev,
      [section]: {
        ...prev[section],
        ...(section === "intro"
          ? {
              template: preset.template,
              speaker: preset.speaker,
              voice_id: preset.voice_id,
              transition_style: preset.transition_style,
              transition_duration: preset.transition_duration,
              transition_volume: preset.transition_volume,
            }
          : {
              mode: preset.mode,
              template: preset.template,
              speaker: preset.speaker,
              voice_id: preset.voice_id,
            }),
      },
    }));
    showToast(`已加载模板「${preset.name}」`, "success");
  };

  const deletePreset = (section, presetId) => {
    if (presetId === "default") {
      showToast("默认模板不能删除", "error");
      return;
    }
    setLocalSettings((prev) => ({
      ...prev,
      [`${section}_presets`]: (prev[`${section}_presets`] || []).filter((p) => p.id !== presetId),
    }));
    showToast("模板已删除", "success");
  };

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
      if (localSettings.body_bgm.custom_path === fileId) {
        updateBodyBgm("custom_path", null);
      }
      showToast("已删除", "success");
    } catch (err) {
      showToast("删除失败", "error");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 size={24} className="animate-spin text-brand-pink" />
      </div>
    );
  }

  return (
    <div className="p-10 max-w-2xl mx-auto">
      <div className="flex items-center gap-4 mb-8">
        <button
          onClick={() => setPage("home")}
          className="flex items-center gap-2 text-xs text-slate-500 hover:text-white transition-colors"
        >
          <ArrowLeft size={14} />
          返回
        </button>
        <div>
          <h1 className="text-2xl font-bold text-white">播客工厂</h1>
          <p className="text-sm text-slate-500 mt-1">管理你的开场白、片尾与背景音乐</p>
        </div>
      </div>

      <div className="flex items-center justify-between mb-6">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2">
          <Music size={16} className="text-brand-pink" />
          节目包装
        </h2>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-pink/10 hover:bg-brand-pink/20 text-brand-pink rounded-lg text-xs font-medium transition-all disabled:opacity-50"
        >
          <Save size={12} />
          {saving ? "保存中..." : "保存到服务端"}
        </button>
      </div>

      <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5 space-y-6">
        {/* Intro */}
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
            <div className="space-y-3 pl-6 border-l border-[#2a2a2a]">
              <div>
                <label className="text-[10px] text-slate-500 mb-1 block">开场白文案（支持 {"{topic}"} 占位符）</label>
                <textarea
                  value={localSettings.intro.template}
                  onChange={(e) => updateIntro("template", e.target.value)}
                  rows={2}
                  className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg p-2.5 text-xs text-white placeholder-slate-600 resize-none outline-none focus:border-brand-pink/30"
                />
              </div>

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

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">过渡时长: {localSettings.intro.transition_duration.toFixed(1)}s</label>
                  <input
                    type="range"
                    min={1}
                    max={8}
                    step={0.5}
                    value={localSettings.intro.transition_duration}
                    onChange={(e) => updateIntro("transition_duration", parseFloat(e.target.value))}
                    className="w-full accent-brand-pink"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-500 mb-1 block">过渡音量: {Math.round(localSettings.intro.transition_volume * 100)}%</label>
                  <input
                    type="range"
                    min={0.05}
                    max={0.3}
                    step={0.01}
                    value={localSettings.intro.transition_volume}
                    onChange={(e) => updateIntro("transition_volume", parseFloat(e.target.value))}
                    className="w-full accent-brand-pink"
                  />
                </div>
              </div>

              <div className="pt-2">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] text-slate-500">开场白模板库</span>
                  <button
                    onClick={() => addPreset("intro")}
                    className="flex items-center gap-1 text-[10px] text-brand-pink hover:text-brand-pink/80 transition-colors"
                  >
                    <Plus size={10} /> 保存当前为模板
                  </button>
                </div>
                <div className="space-y-1.5">
                  {(localSettings.intro_presets || []).map((preset) => (
                    <div
                      key={preset.id}
                      className="flex items-center justify-between bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg px-3 py-2"
                    >
                      <span className="text-xs text-white truncate flex-1">{preset.name}</span>
                      <div className="flex items-center gap-1.5 ml-2">
                        <button
                          onClick={() => loadPreset("intro", preset)}
                          className="p-1 rounded hover:bg-white/5 text-slate-400 hover:text-white transition-colors"
                          title="加载此模板"
                        >
                          <Check size={12} />
                        </button>
                        <button
                          onClick={() => deletePreset("intro", preset.id)}
                          className="p-1 rounded hover:bg-red-500/10 text-slate-400 hover:text-red-400 transition-colors"
                          title="删除"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Outro */}
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
              <div
                className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${
                  localSettings.outro.enabled ? "right-0.5" : "left-0.5"
                }`}
              />
            </button>
          </div>

          {localSettings.outro.enabled && (
            <div className="space-y-3 pl-6 border-l border-[#2a2a2a]">
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

              <div className="pt-2">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] text-slate-500">片尾模板库</span>
                  <button
                    onClick={() => addPreset("outro")}
                    className="flex items-center gap-1 text-[10px] text-brand-pink hover:text-brand-pink/80 transition-colors"
                  >
                    <Plus size={10} /> 保存当前为模板
                  </button>
                </div>
                <div className="space-y-1.5">
                  {(localSettings.outro_presets || []).map((preset) => (
                    <div
                      key={preset.id}
                      className="flex items-center justify-between bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg px-3 py-2"
                    >
                      <span className="text-xs text-white truncate flex-1">{preset.name}</span>
                      <div className="flex items-center gap-1.5 ml-2">
                        <button
                          onClick={() => loadPreset("outro", preset)}
                          className="p-1 rounded hover:bg-white/5 text-slate-400 hover:text-white transition-colors"
                          title="加载此模板"
                        >
                          <Check size={12} />
                        </button>
                        <button
                          onClick={() => deletePreset("outro", preset.id)}
                          className="p-1 rounded hover:bg-red-500/10 text-slate-400 hover:text-red-400 transition-colors"
                          title="删除"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Body BGM */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Music size={14} className="text-brand-tertiary" />
              <span className="text-sm font-medium text-white">正文背景音乐（默认）</span>
            </div>
            <button
              onClick={() => updateBodyBgm("enabled", !localSettings.body_bgm.enabled)}
              className={`w-9 h-5 rounded-full relative cursor-pointer flex-shrink-0 transition-colors ${
                localSettings.body_bgm.enabled ? "bg-brand-pink" : "bg-white/10"
              }`}
            >
              <div
                className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${
                  localSettings.body_bgm.enabled ? "right-0.5" : "left-0.5"
                }`}
              />
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
                      type="range"
                      min={0.02}
                      max={0.2}
                      step={0.01}
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
                        暂无上传的背景音乐，请使用下方按钮上传
                      </div>
                    ) : (
                      <div className="space-y-1.5">
                        {bgmFiles.map((f) => (
                          <div
                            key={f.id}
                            className={`flex items-center justify-between bg-[#1a1a1c] border rounded-lg px-3 py-2 ${
                              localSettings.body_bgm.custom_path === f.id
                                ? "border-brand-pink/30"
                                : "border-[#2a2a2a]"
                            }`}
                          >
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              <Music size={12} className="text-slate-500 flex-shrink-0" />
                              <span className="text-xs text-white truncate">{f.name}</span>
                            </div>
                            <div className="flex items-center gap-1.5 ml-2 flex-shrink-0">
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
                              <button
                                onClick={() => handleDeleteBgm(f.id)}
                                className="p-1 rounded hover:bg-red-500/10 text-slate-400 hover:text-red-400 transition-colors"
                              >
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <div>
                    <input
                      type="file"
                      accept=".mp3,.wav,.m4a,.ogg"
                      onChange={handleBgmUpload}
                      className="hidden"
                      id="bgm-upload-brand"
                    />
                    <button
                      onClick={() => document.getElementById("bgm-upload-brand")?.click()}
                      disabled={uploadingBgm}
                      className="flex items-center gap-1.5 w-full justify-center py-2 rounded-lg bg-white/5 hover:bg-white/10 text-xs text-slate-300 transition-all disabled:opacity-50 border border-dashed border-[#2a2a2a]"
                    >
                      {uploadingBgm ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Upload size={12} />
                      )}
                      {uploadingBgm ? "上传中..." : "上传背景音乐"}
                    </button>
                    <p className="text-[10px] text-slate-600 mt-1 text-center">支持 MP3、WAV、M4A、OGG，建议 30 秒以上</p>
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
