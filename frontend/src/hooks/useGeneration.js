import { useCallback, useRef } from "react";
import {
  generateStreaming,
  getGenerationStatus,
  downloadPodcast,
} from "../api";
import { useAppStore } from "../store";

const STATUS_STEPS = [
  [0, "小羊正在读文章…"],
  [15, "小姜正在做笔记…"],
  [30, "小羊和小姜在讨论…"],
  [50, "小姜在划重点…"],
  [70, "小羊在做总结…"],
  [80, "正在合成语音…"],
  [90, "马上就好了…"],
];

function getStatusText(progress) {
  for (const [p, t] of STATUS_STEPS) {
    if (progress <= p) return t;
  }
  return "马上就好了…";
}

export function useGeneration() {
  const pollTimerRef = useRef(null);

  const setSessionId = useAppStore((s) => s.setSessionId);
  const setGenerationProgress = useAppStore((s) => s.setGenerationProgress);
  const setGenerationStatus = useAppStore((s) => s.setGenerationStatus);
  const setStatusText = useAppStore((s) => s.setStatusText);
  const setPreviewAudioUrl = useAppStore((s) => s.setPreviewAudioUrl);
  const setFullAudioUrl = useAppStore((s) => s.setFullAudioUrl);
  const setCurrentPodcast = useAppStore((s) => s.setCurrentPodcast);
  const setScriptData = useAppStore((s) => s.setScriptData);
  const setTimings = useAppStore((s) => s.setTimings);
  const setGenCount = useAppStore((s) => s.setGenCount);

  const startGeneration = useCallback(
    async (payload) => {
      // Clear previous state
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }

      setGenerationStatus("generating");
      setGenerationProgress(5);
      setStatusText(STATUS_STEPS[0][1]);

      try {
        const { sessionId, blob } = await generateStreaming(payload);
        setSessionId(sessionId);
        setPreviewAudioUrl(URL.createObjectURL(blob));
        setGenerationProgress(40);
        setStatusText("开场已就绪");

        // Start polling
        pollTimerRef.current = setInterval(async () => {
          try {
            const data = await getGenerationStatus(sessionId);
            setGenerationProgress(data.progress || 0);
            setStatusText(getStatusText(data.progress || 0));

            if (data.status === "complete") {
              clearInterval(pollTimerRef.current);
              pollTimerRef.current = null;
              setGenerationStatus("complete");
              setStatusText("已就绪");

              if (data.script) {
                setScriptData(data.script);
                // Build timings
                let acc = 0;
                const t = data.script.map((item) => {
                  const dur = Math.max(1.5, item.text.length / 4);
                  const start = acc;
                  acc += dur;
                  return { start, end: acc };
                });
                setTimings(t);
              }

              if (data.title) {
                setCurrentPodcast({
                  title: data.title,
                  sessionId,
                  platform: data.platform || "网页",
                  time: new Date().toLocaleString("zh-CN"),
                });
              }

              // Increment gen count
              setGenCount((c) => c + 1);

              // Download full audio
              try {
                const fullBlob = await downloadPodcast(sessionId);
                setFullAudioUrl(URL.createObjectURL(fullBlob));
              } catch (e) {
                console.warn("Full audio download failed:", e);
              }
            } else if (data.status === "failed") {
              clearInterval(pollTimerRef.current);
              pollTimerRef.current = null;
              setGenerationStatus("failed");
              setStatusText("生成失败");
            }
          } catch (e) {
            console.warn("Poll error:", e);
          }
        }, 3000);
      } catch (e) {
        setGenerationStatus("failed");
        setStatusText(e.message || "生成失败");
        throw e;
      }
    },
    [
      setSessionId,
      setGenerationProgress,
      setGenerationStatus,
      setStatusText,
      setPreviewAudioUrl,
      setFullAudioUrl,
      setCurrentPodcast,
      setScriptData,
      setTimings,
      setGenCount,
    ]
  );

  const cancelGeneration = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setGenerationStatus("idle");
    setGenerationProgress(0);
    setStatusText("");
  }, [setGenerationStatus, setGenerationProgress, setStatusText]);

  return { startGeneration, cancelGeneration };
}
