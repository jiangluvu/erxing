import { useState, useEffect, useRef } from "react";
import {
  Sparkles,
  Users,
  Zap,
  Loader2,
  PenLine,
  Check,
  Copy,
  Upload,
  FileText,
  Mic,
  ChevronDown,
  Plus,
  X,
  Trash2,
  SlidersHorizontal,
} from "lucide-react";
import { useAppStore } from "../store";
import { getDraft, parseArticle, generateScript, uploadFile, parseScript } from "../api";

const modelLabelMap = {
  "deepseek-v4": "DeepSeek V4", "deepseek-v4-flash": "DeepSeek V4 Flash",
  "gpt-4o": "GPT-4o", "gpt-4o-mini": "GPT-4o Mini",
  "claude-haiku-4-5": "Claude Haiku", "claude-sonnet-4-6": "Claude Sonnet",
  "claude-opus-4-7": "Claude Opus",
  "qwen3-72b": "Qwen3 72B", "qwen3-32b": "Qwen3 32B",
  "gemini-2.5-pro": "Gemini 2.5 Pro",
};
const durationLabelMap = {
  free: "自由适应",
  short: "5–15 分钟",
  long: "15–30 分钟",
  extra_long: "30–60 分钟",
  ultra_long: "60 分钟以上",
};

const tabs = ["链接", "文本", "上传", "我有讲稿", "探索"];

const MALE_VOICES = [
  { id: "639cdf5253a24b50a18cbdb726acce15", name: "默认主持" },
];
const FEMALE_VOICES = [
  { id: "a71b052094fa4505967e262b8cb7d0a6", name: "默认嘉宾" },
];
const EMOTIONS = [
  { value: "正常", label: "正常", desc: "自然平稳" },
  { value: "兴奋", label: "兴奋", desc: "活力上扬" },
  { value: "磁性", label: "磁性", desc: "耳语低沉" },
  { value: "放慢", label: "放慢", desc: "沉稳缓慢" },
  { value: "悲伤", label: "悲伤", desc: "低沉感性" },
];

const placeholders = {
  链接: "粘贴公众号/知乎文章链接，一键生成播客文稿...",
  文本: "粘贴或输入文章正文...",
  上传: "拖拽文章文件到此处，或点击上传...",
  我有讲稿: "粘贴对话稿（主持：...\\n嘉宾：...），或上传文件/图片...",
  探索: "输入你想探讨的话题，AI 帮你写成播客稿件...",
};

export default function ZeroStatePage() {
  const [activeTab, setActiveTab] = useState("链接");
  const [inputValue, setInputValue] = useState("");

  // Draft state (for 探索 tab)
  const [draftResult, setDraftResult] = useState(null);
  const [draftLoading, setDraftLoading] = useState(false);
  const [draftError, setDraftError] = useState(null);
  const [editableDraft, setEditableDraft] = useState("");
  const [copied, setCopied] = useState(false);

  // Script generation loading (for 链接/文本 tabs)
  const [scriptLoading, setScriptLoading] = useState(false);

  // Upload state (for 上传 tab)
  const [uploadLoading, setUploadLoading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  // Script parsing state (for 我有讲稿 tab)
  const [scriptParsing, setScriptParsing] = useState(false);
  const [scriptFile, setScriptFile] = useState(null);
  const [scriptFileName, setScriptFileName] = useState("");

  const setPage = useAppStore((s) => s.setPage);
  const setScriptData = useAppStore((s) => s.setScriptData);
  const showToast = useAppStore((s) => s.showToast);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const selectedDuration = useAppStore((s) => s.selectedDuration);

  // Voice config
  const maleVoiceId = useAppStore((s) => s.maleVoiceId);
  const setMaleVoiceId = useAppStore((s) => s.setMaleVoiceId);
  const femaleVoiceId = useAppStore((s) => s.femaleVoiceId);
  const setFemaleVoiceId = useAppStore((s) => s.setFemaleVoiceId);
  const defaultEmotion = useAppStore((s) => s.defaultEmotion);
  const setDefaultEmotion = useAppStore((s) => s.setDefaultEmotion);
  const customEmotions = useAppStore((s) => s.customEmotions);
  const addCustomEmotion = useAppStore((s) => s.addCustomEmotion);
  const removeCustomEmotion = useAppStore((s) => s.removeCustomEmotion);

  // Fetched voices from Fish Audio
  const [fetchedVoices, setFetchedVoices] = useState([]);

  // Custom dropdown open state
  const [openDropdown, setOpenDropdown] = useState(null);
  // Add emotion form
  const [showAddEmotion, setShowAddEmotion] = useState(false);
  const [newEmotionName, setNewEmotionName] = useState("");
  const [newEmotionTag, setNewEmotionTag] = useState("");

  // Close dropdown on outside click
  const voicePanelRef = useRef(null);
  useEffect(() => {
    const handler = (e) => {
      if (voicePanelRef.current && !voicePanelRef.current.contains(e.target)) {
        setOpenDropdown(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Fetch voices from backend on mount
  useEffect(() => {
    fetch("/api/voices")
      .then((r) => r.json())
      .then((data) => {
        if (data.voices) setFetchedVoices(data.voices);
      })
      .catch(() => {});
  }, []);

  const handleGenerate = async () => {
    const trimmed = inputValue.trim();
    if (!trimmed || trimmed.length < 5) {
      showToast("请输入内容", "error");
      return;
    }

    // "探索" tab: generate article draft
    if (activeTab === "探索") {
      setDraftLoading(true);
      setDraftError(null);
      setDraftResult(null);
      try {
        const result = await getDraft(trimmed);
        setDraftResult(result);
        setEditableDraft(result.draft || "");
      } catch (e) {
        setDraftError(e.message || "稿件生成失败");
        showToast(e.message || "稿件生成失败", "error");
      } finally {
        setDraftLoading(false);
      }
      return;
    }

    // 链接/文本 tabs: parse → generate script → script editor
    const isUrl = trimmed.startsWith("http://") || trimmed.startsWith("https://");
    setScriptLoading(true);
    try {
      showToast("正在解析内容...", "info");
      const parsed = await parseArticle({
        ...(isUrl ? { url: trimmed } : { text: trimmed }),
      });
      showToast("正在生成文稿...", "info");
      const result = await generateScript({
        clean_text: parsed.clean_text,
        model: selectedModel,
        duration: selectedDuration,
      });
      // Apply default emotion override if user selected a non-default style
      const script = result.script || [];
      if (defaultEmotion && defaultEmotion !== "正常") {
        script.forEach((turn) => {
          if (!turn.emotion || turn.emotion === "正常") {
            turn.emotion = defaultEmotion;
          }
        });
      }
      setScriptData(script);
      setPage("scriptEditor");
    } catch (e) {
      showToast(e.message || "生成失败", "error");
    } finally {
      setScriptLoading(false);
    }
  };

  const handleParseScript = async () => {
    if (scriptFile) {
      setScriptParsing(true);
      try {
        const result = await parseScript({ file: scriptFile });
        setScriptData(result.script || []);
        setPage("scriptEditor");
        showToast(`解析成功，共 ${result.total_turns} 轮对话`, "success");
      } catch (e) {
        showToast(e.message || "解析失败", "error");
      } finally {
        setScriptParsing(false);
      }
      return;
    }
    const trimmed = inputValue.trim();
    if (!trimmed || trimmed.length < 5) {
      showToast("请输入对话文稿", "error");
      return;
    }
    if (!trimmed.includes("主持") && !trimmed.includes("嘉宾")) {
      showToast("未识别到对话格式，请确保以「主持：」和「嘉宾：」格式编写", "error");
      return;
    }
    setScriptParsing(true);
    try {
      const result = await parseScript({ text: trimmed });
      setScriptData(result.script || []);
      setPage("scriptEditor");
      showToast(`解析成功，共 ${result.total_turns} 轮对话`, "success");
    } catch (e) {
      showToast(e.message || "解析失败", "error");
    } finally {
      setScriptParsing(false);
    }
  };

  const handleUseDraftForPodcast = () => {
    const text = editableDraft.trim();
    if (!text || text.length < 50) {
      showToast("稿件内容太少，无法生成播客", "error");
      return;
    }
    setActiveTab("文本");
    setInputValue(text);
    setDraftResult(null);
    setEditableDraft("");
    showToast("稿件已填入，点击「生成文稿」生成播客", "success");
  };

  const handleCopyDraft = () => {
    navigator.clipboard.writeText(editableDraft).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleFileUpload = async (file) => {
    if (!file) return;
    const allowed = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain", "text/markdown", "text/csv", "application/json"];
    const allowedExts = [".pdf", ".docx", ".txt", ".md", ".csv", ".json"];
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!allowed.includes(file.type) && !allowedExts.includes(ext)) {
      showToast("不支持的文件格式，请上传 PDF、DOCX 或 TXT", "error");
      return;
    }
    setUploadLoading(true);
    try {
      showToast("正在解析文件...", "info");
      const result = await uploadFile(file);
      setInputValue(result.clean_text || "");
      setActiveTab("文本");
      showToast(`文件解析成功：${result.title || file.name}`, "success");
    } catch (e) {
      showToast(e.message || "文件解析失败", "error");
    } finally {
      setUploadLoading(false);
      setIsDragging(false);
    }
  };

  const onDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const onDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };
  const onDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileUpload(file);
  };

  return (
    <div className="relative overflow-hidden flex flex-col items-center min-h-screen p-10">
      {/* Background glows */}
      <div className="absolute top-[-10%] right-[-5%] w-[600px] h-[600px] bg-brand-pink/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] left-[-5%] w-[400px] h-[400px] bg-[#a9c7ff]/5 rounded-full blur-[100px] pointer-events-none" />

      <div className="max-w-2xl w-full space-y-6 relative z-10">
        {/* Header */}
        <div className="text-center space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10 backdrop-blur-sm">
            <span className="text-[11px] font-bold text-slate-400 tracking-wider">
              知识创作者的 AI 播客引擎
            </span>
            <span className="h-1 w-1 rounded-full bg-brand-pink" />
            <span className="text-[10px] font-black text-brand-pink">NEW</span>
          </div>
          <h1 className="text-white font-bold tracking-tight text-3xl">
            你的文章，值得被听见
          </h1>
          <p className="text-sm text-slate-500">
            4 小时制作 → 5 分钟完成。把深度文章自动变成双人对话播客，直接上架小宇宙。
          </p>
        </div>

        {/* Input Card */}
        <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl overflow-hidden accent-glow transition-all duration-300">
          {/* Tabs */}
          <div className="flex border-b border-[#2a2a2a] bg-[#1a1a1c]">
            {tabs.map((tab) => (
              <button
                key={tab}
                onClick={() => {
                  setActiveTab(tab);
                  if (tab !== "探索") {
                    setDraftResult(null);
                    setDraftError(null);
                  }
                  if (tab !== "我有讲稿") {
                    setScriptFile(null);
                    setScriptFileName("");
                  }
                }}
                className={`px-6 py-4 text-sm font-medium transition-all ${
                  activeTab === tab
                    ? "text-brand-pink border-b-2 border-brand-pink bg-brand-pink/5"
                    : "text-slate-500 hover:text-slate-300"
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Input Area */}
          <div className="p-6">
            {activeTab === "上传" ? (
              <div
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onDrop={onDrop}
                onClick={() => document.getElementById("file-upload")?.click()}
                className={`relative flex flex-col items-center justify-center gap-3 h-40 rounded-xl border-2 border-dashed cursor-pointer transition-all ${
                  isDragging
                    ? "border-brand-pink bg-brand-pink/5"
                    : "border-[#2a2a2a] hover:border-white/20 bg-[#1a1a1c]"
                }`}
              >
                <input
                  id="file-upload"
                  type="file"
                  className="hidden"
                  accept=".pdf,.docx,.txt,.md,.csv,.json"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFileUpload(file);
                    e.target.value = "";
                  }}
                />
                {uploadLoading ? (
                  <>
                    <Loader2 size={24} className="animate-spin text-brand-pink" />
                    <span className="text-sm text-slate-400">正在解析文件...</span>
                  </>
                ) : (
                  <>
                    <Upload size={24} className="text-slate-500" />
                    <span className="text-sm text-slate-400">
                      拖拽文件到此处，或点击上传
                    </span>
                    <span className="text-xs text-slate-600">
                      支持 PDF、DOCX、TXT、MD、CSV、JSON
                    </span>
                  </>
                )}
              </div>
            ) : activeTab === "我有讲稿" ? (
              <div className="space-y-3">
                <textarea
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  className="w-full h-24 bg-[#1a1a1c] border border-[#2a2a2a] rounded-xl p-4 text-sm text-white placeholder-slate-600 resize-y outline-none focus:border-brand-pink/30 transition-all"
                  placeholder={'粘贴对话稿，每行格式：主持：... 或 嘉宾：...\n支持上传文件/图片（见下方）'}
                />
                <div className="flex items-center gap-3">
                  {/* File upload button */}
                  <div className="relative">
                    <input
                      id="script-file-upload"
                      type="file"
                      className="hidden"
                      accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) {
                          if (f.size > 20 * 1024 * 1024) {
                            showToast("文件超过 20MB 限制", "error");
                            return;
                          }
                          setScriptFile(f);
                          setScriptFileName(f.name);
                        }
                        e.target.value = "";
                      }}
                    />
                    <button
                      onClick={() => document.getElementById("script-file-upload")?.click()}
                      className="flex items-center gap-2 px-4 py-2 bg-white/5 border border-[#2a2a2a] hover:border-white/20 rounded-xl text-xs text-slate-400 hover:text-white transition-all"
                    >
                      <Upload size={14} />
                      {scriptFileName ? scriptFileName : "上传文稿文件"}
                    </button>
                  </div>
                  {scriptFileName && (
                    <button
                      onClick={() => { setScriptFile(null); setScriptFileName(""); }}
                      className="text-xs text-red-400 hover:text-red-300"
                    >
                      清除
                    </button>
                  )}
                  <span className="text-[10px] text-slate-600">
                    支持 TXT / PDF / DOCX / 图片
                  </span>
                </div>
              </div>
            ) : (
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                className="w-full h-32 bg-transparent border-none focus:ring-0 text-white placeholder-slate-600 resize-none text-sm outline-none"
                placeholder={placeholders[activeTab]}
              />
            )}
          </div>
          {/* Footer */}
          <div className="px-6 py-3 border-t border-[#2a2a2a] flex items-center justify-between">
            <button
              onClick={() => setPage("settings")}
              className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              <SlidersHorizontal size={14} />
              <span>生成设置</span>
            </button>
            <button
              onClick={() => setPage("settings")}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              {modelLabelMap[selectedModel] || "DeepSeek"} · {durationLabelMap[selectedDuration] || "自由适应"}
            </button>
          </div>
        </div>

        {/* Draft Result */}
        {draftLoading && (
          <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-8 text-center">
            <Loader2 size={24} className="animate-spin text-brand-pink mx-auto mb-3" />
            <p className="text-sm text-slate-400">AI 正在根据知识库撰写稿件...</p>
          </div>
        )}

        {draftError && (
          <div className="bg-[#161618] border border-red-500/20 rounded-2xl p-6 text-center">
            <p className="text-sm text-red-400">{draftError}</p>
            <button
              onClick={handleGenerate}
              className="mt-3 text-xs text-brand-pink hover:underline"
            >
              重试
            </button>
          </div>
        )}

        {draftResult && !draftLoading && (
          <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2a] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <PenLine size={16} className="text-brand-pink" />
                <span className="text-sm font-medium text-white">AI 生成的稿件</span>
              </div>
              <button
                onClick={handleCopyDraft}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-white/5 text-slate-400 hover:text-white transition-all"
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                <span>{copied ? "已复制" : "复制"}</span>
              </button>
            </div>
            <div className="p-6">
              <textarea
                value={editableDraft}
                onChange={(e) => setEditableDraft(e.target.value)}
                className="w-full h-64 bg-[#1a1a1c] border border-[#2a2a2a] rounded-xl p-4 text-sm text-white placeholder-slate-600 resize-y outline-none focus:border-brand-pink/30 transition-all"
              />
            </div>

            {draftResult.references && draftResult.references.length > 0 && (
              <div className="px-6 pb-2">
                <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-2">参考来源</p>
                <div className="space-y-1">
                  {draftResult.references.map((ref, i) => (
                    <div key={i} className="text-xs text-slate-500">
                      <span className="text-slate-400">{ref.title}</span>
                      {ref.url && <span className="ml-2 text-brand-pink/60">↗</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="px-6 py-4 border-t border-[#2a2a2a] flex justify-end">
              <button
                onClick={handleUseDraftForPodcast}
                className="flex items-center gap-2 px-6 py-2.5 bg-brand-pink hover:bg-brand-pink/80 text-white rounded-xl text-sm font-medium transition-all"
              >
                <Sparkles size={16} />
                <span>使用此稿件生成播客</span>
              </button>
            </div>
          </div>
        )}

        {/* Voice & Emotion Config — always visible */}
        <div ref={voicePanelRef} className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-5 space-y-4">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-400">
            <Mic size={14} className="text-brand-pink" />
            <span>音色与情绪设置</span>
          </div>

          <div className="grid grid-cols-3 gap-4">
            {/* Male Voice */}
            <div className="relative">
              <label className="text-[10px] text-slate-500 mb-1.5 block">主持音色</label>
              <button
                onClick={() => setOpenDropdown(openDropdown === "male" ? null : "male")}
                className="w-full flex items-center justify-between bg-[#1a1a1c] border border-[#2a2a2a] hover:border-white/20 rounded-lg py-2 px-3 text-xs text-white transition-all"
              >
                <span>
                  {[...MALE_VOICES, ...fetchedVoices].find((v) => v.id === maleVoiceId)?.title ||
                   [...MALE_VOICES, ...fetchedVoices].find((v) => v.id === maleVoiceId)?.name ||
                   "选择音色"}
                </span>
                <ChevronDown size={12} className={`text-slate-500 transition-transform ${openDropdown === "male" ? "rotate-180" : ""}`} />
              </button>
              {openDropdown === "male" && (
                <div className="absolute z-20 mt-1 w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg shadow-xl overflow-hidden max-h-48 overflow-y-auto">
                  {[...MALE_VOICES, ...fetchedVoices].map((v) => (
                    <div key={v.id} className="flex items-center justify-between px-3 py-2 hover:bg-white/5 cursor-pointer transition-colors">
                      <span className="text-xs text-white flex-1" onClick={() => { setMaleVoiceId(v.id); setOpenDropdown(null); }}>
                        {v.title || v.name}
                      </span>
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

            {/* Female Voice */}
            <div className="relative">
              <label className="text-[10px] text-slate-500 mb-1.5 block">嘉宾音色</label>
              <button
                onClick={() => setOpenDropdown(openDropdown === "female" ? null : "female")}
                className="w-full flex items-center justify-between bg-[#1a1a1c] border border-[#2a2a2a] hover:border-white/20 rounded-lg py-2 px-3 text-xs text-white transition-all"
              >
                <span>
                  {[...FEMALE_VOICES, ...fetchedVoices].find((v) => v.id === femaleVoiceId)?.title ||
                   [...FEMALE_VOICES, ...fetchedVoices].find((v) => v.id === femaleVoiceId)?.name ||
                   "选择音色"}
                </span>
                <ChevronDown size={12} className={`text-slate-500 transition-transform ${openDropdown === "female" ? "rotate-180" : ""}`} />
              </button>
              {openDropdown === "female" && (
                <div className="absolute z-20 mt-1 w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg shadow-xl overflow-hidden max-h-48 overflow-y-auto">
                  {[...FEMALE_VOICES, ...fetchedVoices].map((v) => (
                    <div key={v.id} className="flex items-center justify-between px-3 py-2 hover:bg-white/5 cursor-pointer transition-colors">
                      <span className="text-xs text-white flex-1" onClick={() => { setFemaleVoiceId(v.id); setOpenDropdown(null); }}>
                        {v.title || v.name}
                      </span>
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

            {/* Emotion */}
            <div className="relative">
              <label className="text-[10px] text-slate-500 mb-1.5 block">情绪基调</label>
              <button
                onClick={() => setOpenDropdown(openDropdown === "emotion" ? null : "emotion")}
                className="w-full flex items-center justify-between bg-[#1a1a1c] border border-[#2a2a2a] hover:border-white/20 rounded-lg py-2 px-3 text-xs text-white transition-all"
              >
                <span>
                  {[...EMOTIONS, ...customEmotions].find((e) => e.value === defaultEmotion)?.label || "选择情绪"}
                </span>
                <ChevronDown size={12} className={`text-slate-500 transition-transform ${openDropdown === "emotion" ? "rotate-180" : ""}`} />
              </button>
              {openDropdown === "emotion" && (
                <div className="absolute z-20 mt-1 w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg shadow-xl overflow-hidden max-h-48 overflow-y-auto">
                  {[...EMOTIONS, ...customEmotions].map((e) => (
                    <div key={e.value} className="flex items-center justify-between px-3 py-2 hover:bg-white/5 cursor-pointer transition-colors">
                      <span className="text-xs text-white flex-1" onClick={() => { setDefaultEmotion(e.value); setOpenDropdown(null); }}>
                        {e.label} <span className="text-slate-500">· {e.desc}</span>
                      </span>
                      {customEmotions.some((ce) => ce.value === e.value) && (
                        <button
                          onClick={(e) => { e.stopPropagation(); removeCustomEmotion(e.value); if (defaultEmotion === e.value) setDefaultEmotion("正常"); }}
                          className="p-1 text-slate-500 hover:text-red-400 transition-colors"
                        >
                          <Trash2 size={10} />
                        </button>
                      )}
                    </div>
                  ))}
                  <button
                    onClick={() => { setShowAddEmotion(!showAddEmotion); }}
                    className="w-full flex items-center gap-1.5 px-3 py-2 text-[10px] text-brand-pink hover:bg-brand-pink/10 transition-colors border-t border-[#2a2a2a]"
                  >
                    <Plus size={10} /> 添加情绪
                  </button>
                  {showAddEmotion && (
                    <div className="px-3 py-2 space-y-2 border-t border-[#2a2a2a] bg-[#161618]">
                      <input
                        value={newEmotionName}
                        onChange={(e) => setNewEmotionName(e.target.value)}
                        placeholder="显示名称（如：温柔）"
                        className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded py-1 px-2 text-[10px] text-white outline-none focus:border-brand-pink/30"
                      />
                      <input
                        value={newEmotionTag}
                        onChange={(e) => setNewEmotionTag(e.target.value)}
                        placeholder="Fish Audio 标签（如：speaking softly）"
                        className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded py-1 px-2 text-[10px] text-white outline-none focus:border-brand-pink/30"
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={() => {
                            if (newEmotionName.trim() && newEmotionTag.trim()) {
                              addCustomEmotion({ value: newEmotionTag.trim(), label: newEmotionName.trim(), desc: "自定义" });
                              setNewEmotionName(""); setNewEmotionTag(""); setShowAddEmotion(false);
                            }
                          }}
                          className="flex-1 py-1 bg-brand-pink/10 text-brand-pink rounded text-[10px] font-medium hover:bg-brand-pink/20 transition-colors"
                        >
                          保存
                        </button>
                        <button
                          onClick={() => { setShowAddEmotion(false); setNewEmotionName(""); setNewEmotionTag(""); }}
                          className="flex-1 py-1 bg-white/5 text-slate-400 rounded text-[10px] hover:bg-white/10 transition-colors"
                        >
                          取消
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Primary CTA */}
        <div className="flex flex-col items-center gap-6 pt-3">
          <button
            onClick={activeTab === "我有讲稿" ? handleParseScript : handleGenerate}
            disabled={scriptLoading || draftLoading || scriptParsing}
            className="group relative flex items-center gap-3 px-12 py-4 bg-white hover:bg-white/90 disabled:bg-white/60 text-black rounded-full font-bold text-lg transition-all active:scale-95 shadow-[0_0_40px_rgba(255,255,255,0.1)] disabled:cursor-not-allowed"
          >
            {scriptLoading || draftLoading || scriptParsing ? (
              <Loader2 size={20} className="animate-spin" />
            ) : (
              <Sparkles size={20} />
            )}
            <span>
              {scriptLoading
                ? "正在生成文稿..."
                : draftLoading
                ? "正在生成稿件..."
                : scriptParsing
                ? "正在解析讲稿..."
                : activeTab === "我有讲稿"
                ? "解析讲稿"
                : activeTab === "探索"
                ? "生成稿件"
                : "生成文稿"}
            </span>
          </button>
          <div className="flex items-center gap-8">
            <a
              className="text-xs text-slate-500 hover:text-brand-pink transition-colors underline underline-offset-4"
              href="#"
              onClick={(e) => {
                e.preventDefault();
                setPage("hot");
              }}
            >
              创作灵感
            </a>
            <a
              className="text-xs text-slate-500 hover:text-brand-pink transition-colors underline underline-offset-4"
              href="#"
              onClick={(e) => {
                e.preventDefault();
                setPage("myPodcasts");
              }}
            >
              我的内容
            </a>
          </div>
        </div>

        {/* Feature Showcase Bento */}
        <div className="grid grid-cols-2 gap-4 mt-10">
          <div className="p-6 rounded-2xl bg-white/5 border border-white/5 flex flex-col gap-3">
            <div className="h-10 w-10 rounded-xl bg-brand-pink/10 flex items-center justify-center">
              <Users size={20} className="text-brand-pink" />
            </div>
            <h4 className="text-white font-semibold text-sm">AI 演绎文章观点</h4>
            <p className="text-xs text-slate-500 leading-relaxed">
              AI 自动提取文章核心论点，生成主持人与嘉宾的深度对谈。不是单调朗读，而是有论证、有例子的互动演绎，完播率远高于单人播报。
            </p>
          </div>
          <div className="p-6 rounded-2xl bg-white/5 border border-white/5 flex flex-col gap-3">
            <div className="h-10 w-10 rounded-xl bg-brand-tertiary/10 flex items-center justify-center">
              <Zap size={20} className="text-brand-tertiary" />
            </div>
            <h4 className="text-white font-semibold text-sm">分钟级内容生产</h4>
            <p className="text-xs text-slate-500 leading-relaxed">
              从文章链接到可发布播客只需 5 分钟。响度标准化 + 智能音频后处理，直接达到小宇宙、喜马拉雅发布标准，无需二次剪辑。
            </p>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="absolute bottom-10 text-center w-full">
        <p className="text-[10px] text-slate-700 tracking-widest uppercase">
          播刻 v2.0.4 — The Luminescent Guide
        </p>
      </footer>
    </div>
  );
}
