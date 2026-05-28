import { useState, useEffect, useRef } from "react";
import {
  Mic,
  Trash2,
  Upload,
  Loader2,
  ArrowLeft,
  Check,
  Volume2,
  AlertCircle,
} from "lucide-react";
import { useAppStore } from "../store";

const API_BASE = "/api";

async function fetchJSON(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

export default function MyVoicesPage() {
  const setPage = useAppStore((s) => s.setPage);
  const showToast = useAppStore((s) => s.showToast);
  const maleVoiceId = useAppStore((s) => s.maleVoiceId);
  const setMaleVoiceId = useAppStore((s) => s.setMaleVoiceId);
  const femaleVoiceId = useAppStore((s) => s.femaleVoiceId);
  const setFemaleVoiceId = useAppStore((s) => s.setFemaleVoiceId);

  const [voices, setVoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newGender, setNewGender] = useState("male");
  const [selectedFile, setSelectedFile] = useState(null);
  const fileInputRef = useRef(null);

  const loadVoices = async () => {
    setLoading(true);
    try {
      const data = await fetchJSON("/voices");
      setVoices(data.voices || []);
    } catch (e) {
      showToast(e.message || "获取音色列表失败", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadVoices();
  }, []);

  const handleFileSelect = (file) => {
    if (!file) return;
    const allowed = ["audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp3", "audio/ogg", "audio/flac"];
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    const allowedExts = [".mp3", ".wav", ".ogg", ".flac", ".m4a"];
    if (!allowed.includes(file.type) && !allowedExts.includes(ext)) {
      showToast("不支持的音频格式，请上传 MP3、WAV、OGG、FLAC", "error");
      return;
    }
    setSelectedFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile || !newTitle.trim()) {
      showToast("请填写音色名称并选择音频文件", "error");
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("audio", selectedFile);
      formData.append("title", newTitle.trim());
      formData.append("gender", newGender);
      const res = await fetch(`${API_BASE}/voices`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      const data = await res.json();
      showToast("音色创建成功！", "success");
      // Auto-set as default for selected gender
      if (newGender === "male") {
        setMaleVoiceId(data.voice.id);
      } else {
        setFemaleVoiceId(data.voice.id);
      }
      setNewTitle("");
      setSelectedFile(null);
      await loadVoices();
    } catch (e) {
      showToast(e.message || "创建音色失败", "error");
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (voiceId) => {
    if (!confirm("确定要删除这个音色吗？此操作不可撤销。")) return;
    try {
      const res = await fetch(`${API_BASE}/voices/${encodeURIComponent(voiceId)}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("删除失败");
      showToast("音色已删除", "success");
      if (maleVoiceId === voiceId) setMaleVoiceId("639cdf5253a24b50a18cbdb726acce15");
      if (femaleVoiceId === voiceId) setFemaleVoiceId("a71b052094fa4505967e262b8cb7d0a6");
      await loadVoices();
    } catch (e) {
      showToast(e.message || "删除失败", "error");
    }
  };

  return (
    <div className="p-10 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <div>
          <h1 className="text-xl font-bold text-white">我的声音</h1>
          <p className="text-xs text-slate-500 mt-1">
            管理你在 Fish Audio 上的自定义音色
          </p>
        </div>
      </div>

      {/* Upload Card */}
      <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-6 mb-6 space-y-4">
        <div className="flex items-center gap-2 text-sm font-medium text-white">
          <Upload size={16} className="text-brand-pink" />
          <span>录入新音色</span>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-[10px] text-slate-500 mb-1.5 block">音色名称</label>
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="例如：我的主持音色"
              className="w-full bg-[#1a1a1c] border border-[#2a2a2a] rounded-lg py-2 px-3 text-xs text-white placeholder-slate-600 outline-none focus:border-brand-pink/30 transition-all"
            />
          </div>
          <div>
            <label className="text-[10px] text-slate-500 mb-1.5 block">性别</label>
            <div className="flex gap-2">
              <button
                onClick={() => setNewGender("male")}
                className={`flex-1 py-2 rounded-lg text-xs font-medium transition-all ${
                  newGender === "male"
                    ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                    : "bg-[#1a1a1c] border border-[#2a2a2a] text-slate-400 hover:text-white"
                }`}
              >
                主持
              </button>
              <button
                onClick={() => setNewGender("female")}
                className={`flex-1 py-2 rounded-lg text-xs font-medium transition-all ${
                  newGender === "female"
                    ? "bg-brand-tertiary/10 text-brand-tertiary border border-brand-tertiary/20"
                    : "bg-[#1a1a1c] border border-[#2a2a2a] text-slate-400 hover:text-white"
                }`}
              >
                嘉宾
              </button>
            </div>
          </div>
        </div>

        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={(e) => { e.preventDefault(); setDragOver(false); }}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const file = e.dataTransfer.files?.[0];
            if (file) handleFileSelect(file);
          }}
          onClick={() => fileInputRef.current?.click()}
          className={`relative flex flex-col items-center justify-center gap-2 h-28 rounded-xl border-2 border-dashed cursor-pointer transition-all ${
            dragOver
              ? "border-brand-pink bg-brand-pink/5"
              : "border-[#2a2a2a] hover:border-white/20 bg-[#1a1a1c]"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".mp3,.wav,.ogg,.flac,.m4a"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFileSelect(file);
              e.target.value = "";
            }}
          />
          {selectedFile ? (
            <>
              <Check size={20} className="text-brand-pink" />
              <span className="text-xs text-white">{selectedFile.name}</span>
              <span className="text-[10px] text-slate-500">
                {(selectedFile.size / 1024 / 1024).toFixed(2)} MB · 点击更换
              </span>
            </>
          ) : (
            <>
              <Volume2 size={20} className="text-slate-500" />
              <span className="text-xs text-slate-400">拖拽音频到此处，或点击上传</span>
              <span className="text-[10px] text-slate-600">支持 MP3、WAV、OGG、FLAC（建议 10-30 秒）</span>
            </>
          )}
        </div>

        <button
          onClick={handleUpload}
          disabled={uploading || !selectedFile || !newTitle.trim()}
          className="w-full flex items-center justify-center gap-2 py-3 bg-brand-pink hover:bg-brand-pink/80 disabled:bg-brand-pink/40 text-white rounded-xl text-sm font-bold transition-all"
        >
          {uploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
          <span>{uploading ? "上传并训练中..." : "创建音色"}</span>
        </button>
      </div>

      {/* Voice List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-medium text-white">已创建音色</h2>
          <button
            onClick={loadVoices}
            className="text-[10px] text-slate-500 hover:text-brand-pink transition-colors"
          >
            刷新列表
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={24} className="animate-spin text-brand-pink" />
          </div>
        ) : voices.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-slate-500">
            <AlertCircle size={32} className="mb-3 text-slate-600" />
            <p className="text-sm">还没有创建音色</p>
            <p className="text-[10px] mt-1">上传一段 10-30 秒的音频即可创建</p>
          </div>
        ) : (
          voices.map((voice) => (
            <div
              key={voice.id}
              className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-4 flex items-center gap-4 hover:border-white/10 transition-all"
            >
              <div className="h-10 w-10 rounded-xl bg-brand-pink/10 flex items-center justify-center flex-shrink-0">
                <Mic size={18} className="text-brand-pink" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-white truncate">{voice.title}</span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                      voice.state === "trained"
                        ? "bg-green-500/10 text-green-400"
                        : "bg-yellow-500/10 text-yellow-400"
                    }`}
                  >
                    {voice.state === "trained" ? "已就绪" : voice.state}
                  </span>
                  {maleVoiceId === voice.id && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-brand-pink/10 text-brand-pink">
                      当前主持
                    </span>
                  )}
                  {femaleVoiceId === voice.id && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-brand-tertiary/10 text-brand-tertiary">
                      当前嘉宾
                    </span>
                  )}
                </div>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  {voice.languages?.join(", ")} · {voice.id}
                </p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={() => setMaleVoiceId(voice.id)}
                  className={`px-3 py-1.5 rounded-lg text-[10px] font-medium transition-all ${
                    maleVoiceId === voice.id
                      ? "bg-brand-pink/10 text-brand-pink border border-brand-pink/20"
                      : "bg-white/5 text-slate-400 hover:text-white border border-transparent"
                  }`}
                >
                  设为主持
                </button>
                <button
                  onClick={() => setFemaleVoiceId(voice.id)}
                  className={`px-3 py-1.5 rounded-lg text-[10px] font-medium transition-all ${
                    femaleVoiceId === voice.id
                      ? "bg-brand-tertiary/10 text-brand-tertiary border border-brand-tertiary/20"
                      : "bg-white/5 text-slate-400 hover:text-white border border-transparent"
                  }`}
                >
                  设为嘉宾
                </button>
                <button
                  onClick={() => handleDelete(voice.id)}
                  className="p-2 rounded-lg bg-white/5 text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-all"
                  title="删除"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
