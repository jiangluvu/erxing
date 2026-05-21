import { useRef, useCallback, useState } from "react";
import { useAppStore } from "../store";
import { usePlayer } from "../hooks/usePlayer";
import { useGeneration } from "../hooks/useGeneration";
import { addFavorite, downloadPodcast, reportUserAction } from "../api";
import {
  ArrowLeft,
  Heart,
  Download,
  Share2,
  SkipBack,
  Rewind,
  Play,
  Pause,
  FastForward,
  SkipForward,
  User,
  Sparkles,
} from "lucide-react";

function formatTime(s) {
  if (!s || isNaN(s)) return "00:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export default function PlayerPage() {
  const setPage = useAppStore((s) => s.setPage);
  const currentPodcast = useAppStore((s) => s.currentPodcast);
  const isPlaying = useAppStore((s) => s.isPlaying);
  const currentTime = useAppStore((s) => s.currentTime);
  const duration = useAppStore((s) => s.duration);
  const scriptData = useAppStore((s) => s.scriptData);
  const activeTranscriptIndex = useAppStore((s) => s.activeTranscriptIndex);
  const sessionId = useAppStore((s) => s.sessionId);
  const showToast = useAppStore((s) => s.showToast);

  const { togglePlay, seek, seekRelative } = usePlayer();
  const { startGeneration } = useGeneration();
  const progressRef = useRef(null);
  const [favorited, setFavorited] = useState(false);
  const replayReportedRef = useRef(false);

  const fullAudioUrl = useAppStore((s) => s.fullAudioUrl);
  const previewAudioUrl = useAppStore((s) => s.previewAudioUrl);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const selectedDuration = useAppStore((s) => s.selectedDuration);
  const highQuality = useAppStore((s) => s.highQuality);
  const bgMusic = useAppStore((s) => s.bgMusic);
  const hasAudio = fullAudioUrl || previewAudioUrl;

  // Report replay when existing full podcast is played again
  useEffect(() => {
    if (fullAudioUrl && sessionId && currentPodcast && !replayReportedRef.current) {
      replayReportedRef.current = true;
      reportUserAction({
        session_id: sessionId,
        action_type: "replay",
        article_title: currentPodcast.title || "",
        platform: currentPodcast.platform || "",
      });
    }
  }, [fullAudioUrl, sessionId, currentPodcast]);

  const handleGenerateFromPlayer = async () => {
    const topic = currentPodcast?.title || "";
    if (!topic) return;
    // Report regenerate action
    reportUserAction({
      session_id: sessionId,
      action_type: "regenerate",
      article_title: topic,
    });
    const payload = {
      text: topic,
      model: selectedModel,
      duration: selectedDuration,
      high_quality: highQuality,
      bg_music: bgMusic,
    };
    try {
      await startGeneration(payload);
      setPage("generation");
    } catch (e) {
      showToast(e.message || "生成失败", "error");
    }
  };

  const [downloading, setDownloading] = useState(false);

  const handleFavorite = async () => {
    if (!sessionId) return;
    try {
      await addFavorite(sessionId);
      setFavorited(true);
    } catch {
      setFavorited((v) => !v);
    }
  };

  const handleDownload = async () => {
    if (!sessionId || downloading) return;
    setDownloading(true);
    try {
      const blob = await downloadPodcast(sessionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${currentPodcast?.title || "podcast"}.mp3`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      showToast(e.message || "下载失败", "error");
    } finally {
      setDownloading(false);
    }
  };

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  const handleProgressClick = useCallback(
    (e) => {
      if (!progressRef.current || !duration) return;
      const rect = progressRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const p = Math.max(0, Math.min(1, x / rect.width));
      seek(p * duration);
    },
    [duration, seek]
  );

  const handleProgressDrag = useCallback(
    (e) => {
      if (!progressRef.current || !duration) return;
      const rect = progressRef.current.getBoundingClientRect();

      const update = (clientX) => {
        const x = clientX - rect.left;
        const p = Math.max(0, Math.min(1, x / rect.width));
        seek(p * duration);
      };

      const onMove = (ev) => update(ev.clientX);
      const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      };

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    },
    [duration, seek]
  );

  return (
    <div className="flex flex-col h-screen">
      {/* Top Bar */}
      <div className="flex items-center gap-4 px-8 py-4 border-b border-[#2a2a2a] flex-shrink-0">
        <button
          onClick={() => setPage("home")}
          className="p-2 rounded-lg hover:bg-white/5 text-slate-400 hover:text-white transition-all"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="text-sm font-semibold text-white truncate">
            {currentPodcast?.title || "文章播客"}
          </h1>
          <p className="text-xs text-slate-500">
            {currentPodcast?.platform || "网页"} · {currentPodcast?.time || "刚刚"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleFavorite}
            className={`p-2 rounded-lg hover:bg-white/5 transition-all ${
              favorited ? "text-brand-pink" : "text-slate-400 hover:text-white"
            }`}
          >
            <Heart size={18} fill={favorited ? "currentColor" : "none"} />
          </button>
          <button
            onClick={handleDownload}
            disabled={downloading}
            className={`p-2 rounded-lg hover:bg-white/5 transition-all ${
              downloading ? "text-brand-pink" : "text-slate-400 hover:text-white"
            }`}
          >
            <Download size={18} />
          </button>
          <button className="p-2 rounded-lg hover:bg-white/5 text-slate-400 hover:text-white transition-all">
            <Share2 size={18} />
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Player */}
        <div className="flex-1 flex flex-col items-center justify-center p-10">
          {/* Avatars */}
          <div className="flex items-center gap-12 mb-10">
            <div className="text-center">
              <div className="relative w-20 h-20 mx-auto mb-3">
                <div
                  className={`w-20 h-20 rounded-full flex items-center justify-center transition-all ${
                    activeTranscriptIndex >= 0 &&
                    scriptData?.[activeTranscriptIndex]?.speaker === "主持"
                      ? "bg-brand-pink/10 text-brand-pink ring-2 ring-brand-pink/50"
                      : "bg-white/5 text-slate-400"
                  }`}
                >
                  <User size={32} />
                </div>
              </div>
              <div className="text-sm font-semibold text-white">主持</div>
              <div
                className={`text-xs mt-0.5 ${
                  activeTranscriptIndex >= 0 &&
                  scriptData?.[activeTranscriptIndex]?.speaker === "主持"
                    ? "text-brand-pink"
                    : "text-slate-500"
                }`}
              >
                {activeTranscriptIndex >= 0 &&
                scriptData?.[activeTranscriptIndex]?.speaker === "主持"
                  ? "正在说话"
                  : "等待中"}
              </div>
            </div>
            <div className="text-center">
              <div className="relative w-20 h-20 mx-auto mb-3">
                <div
                  className={`w-20 h-20 rounded-full flex items-center justify-center transition-all ${
                    activeTranscriptIndex >= 0 &&
                    scriptData?.[activeTranscriptIndex]?.speaker === "嘉宾"
                      ? "bg-brand-tertiary/10 text-brand-tertiary ring-2 ring-brand-tertiary/50"
                      : "bg-white/5 text-slate-400"
                  }`}
                >
                  <User size={32} />
                </div>
              </div>
              <div className="text-sm font-semibold text-white">嘉宾</div>
              <div
                className={`text-xs mt-0.5 ${
                  activeTranscriptIndex >= 0 &&
                  scriptData?.[activeTranscriptIndex]?.speaker === "嘉宾"
                    ? "text-brand-tertiary"
                    : "text-slate-500"
                }`}
              >
                {activeTranscriptIndex >= 0 &&
                scriptData?.[activeTranscriptIndex]?.speaker === "嘉宾"
                  ? "正在说话"
                  : "等待中"}
              </div>
            </div>
          </div>

          {/* Waveform bars */}
          <div className="w-full max-w-md mb-8 flex items-center justify-center gap-0.5 h-12">
            {Array.from({ length: 15 }).map((_, i) => (
              <div
                key={i}
                className="w-1 bg-brand-pink/60 rounded-full"
                style={{
                  height: `${30 + Math.random() * 60}%`,
                  animation: isPlaying
                    ? `bounce ${0.8 + Math.random() * 0.6}s ease-in-out infinite`
                    : "none",
                  animationDelay: `${i * 0.05}s`,
                }}
              />
            ))}
          </div>

          {/* Progress + Controls */}
          <div className="w-full max-w-md">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
              <span>{formatTime(currentTime)}</span>
              <span>{formatTime(duration)}</span>
            </div>
            <div
              ref={progressRef}
              className="h-1.5 bg-white/5 rounded-full overflow-hidden cursor-pointer mb-6"
              onClick={handleProgressClick}
              onMouseDown={handleProgressDrag}
            >
              <div
                className="h-full rounded-full bg-gradient-to-r from-brand-pink to-brand-tertiary"
                style={{ width: `${progress}%` }}
              />
            </div>
            {hasAudio ? (
              <div className="flex items-center justify-center gap-6">
                <button
                  onClick={() => seekRelative(-15)}
                  className="p-3 rounded-full hover:bg-white/5 text-slate-400 hover:text-white transition-all"
                >
                  <Rewind size={20} />
                </button>
                <button
                  onClick={togglePlay}
                  className="w-14 h-14 rounded-full bg-white flex items-center justify-center text-black hover:bg-white/90 transition-all shadow-[0_0_30px_rgba(255,255,255,0.1)]"
                >
                  {isPlaying ? (
                    <Pause size={24} />
                  ) : (
                    <Play size={24} className="ml-0.5" />
                  )}
                </button>
                <button
                  onClick={() => seekRelative(15)}
                  className="p-3 rounded-full hover:bg-white/5 text-slate-400 hover:text-white transition-all"
                >
                  <FastForward size={20} />
                </button>
              </div>
            ) : (
              <button
                onClick={handleGenerateFromPlayer}
                className="group relative flex items-center gap-3 px-10 py-3.5 bg-white hover:bg-white/90 text-black rounded-full font-bold text-base transition-all active:scale-95 shadow-[0_0_40px_rgba(255,255,255,0.1)]"
              >
                <Sparkles size={18} />
                <span>生成完整播客</span>
              </button>
            )}
          </div>
        </div>

        {/* Right: Transcript */}
        <div className="w-[380px] border-l border-[#2a2a2a] flex flex-col bg-[#0c0c0e]">
          <div className="px-5 py-4 border-b border-[#2a2a2a] flex items-center justify-between flex-shrink-0">
            <h3 className="text-sm font-semibold text-white">对话文稿</h3>
            <span className="text-xs text-slate-500">
              共 {scriptData?.length || 0} 段
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-5 space-y-3">
            {scriptData?.length ? (
              scriptData.map((item, i) => {
                const isActive = i === activeTranscriptIndex;
                const isYang = item.speaker === "主持";
                return (
                  <div
                    key={i}
                    className={`flex gap-3 p-3 rounded-xl transition-all ${
                      isActive
                        ? "bg-white/5 border-l-2 border-brand-pink"
                        : ""
                    }`}
                  >
                    <span
                      className={`text-xs font-bold flex-shrink-0 pt-0.5 ${
                        isYang ? "text-brand-pink" : "text-slate-500"
                      }`}
                    >
                      {item.speaker === "主持" ? "主持" : "嘉宾"}
                    </span>
                    <p
                      className={`text-sm leading-relaxed ${
                        isActive ? "text-white" : "text-slate-400"
                      }`}
                    >
                      {item.text}
                    </p>
                  </div>
                );
              })
            ) : (
              <div className="flex gap-3 p-3 rounded-xl">
                <span className="text-sm text-slate-500">文稿加载中…</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
