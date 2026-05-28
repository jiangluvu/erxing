import { useCallback } from "react";
import {
  generateStreaming,
  downloadPodcast,
} from "../api";
import { useAppStore } from "../store";

export function useGeneration() {
  const setSessionId = useAppStore((s) => s.setSessionId);
  const setGenerationProgress = useAppStore((s) => s.setGenerationProgress);
  const setGenerationStatus = useAppStore((s) => s.setGenerationStatus);
  const setStatusText = useAppStore((s) => s.setStatusText);
  const setPreviewAudioUrl = useAppStore((s) => s.setPreviewAudioUrl);

  const startGeneration = useCallback(
    async (payload) => {
      // Inject selected intro/outro preset IDs
      const state = useAppStore.getState();
      if (state.selectedIntroPresetId) {
        payload.intro_preset_id = state.selectedIntroPresetId;
      }
      if (state.selectedOutroPresetId) {
        payload.outro_preset_id = state.selectedOutroPresetId;
      }

      // Clear previous session — triggers App-level poll cleanup
      setSessionId(null);
      setGenerationProgress(0);
      setGenerationStatus("generating");
      setGenerationProgress(5);
      setStatusText("主持正在读文章…");

      try {
        const { sessionId, blob } = await generateStreaming(payload);
        setSessionId(sessionId);
        setPreviewAudioUrl(URL.createObjectURL(blob));
        setGenerationProgress(40);
        setStatusText("开场已就绪");
        // Polling is handled at App.jsx level — persists across page navigation
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
    ]
  );

  const cancelGeneration = useCallback(() => {
    setSessionId(null);
    setGenerationStatus("idle");
    setGenerationProgress(0);
    setStatusText("");
  }, [setSessionId, setGenerationStatus, setGenerationProgress, setStatusText]);

  return { startGeneration, cancelGeneration };
}