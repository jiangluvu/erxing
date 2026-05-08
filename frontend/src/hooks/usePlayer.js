import { useCallback, useEffect, useRef } from "react";
import { useAppStore } from "../store";
import { addHistory } from "../api";

export function usePlayer() {
  const audioRef = useRef(null);
  const lastReportRef = useRef(0);

  const isPlaying = useAppStore((s) => s.isPlaying);
  const setIsPlaying = useAppStore((s) => s.setIsPlaying);
  const setCurrentTime = useAppStore((s) => s.setCurrentTime);
  const setDuration = useAppStore((s) => s.setDuration);
  const previewAudioUrl = useAppStore((s) => s.previewAudioUrl);
  const fullAudioUrl = useAppStore((s) => s.fullAudioUrl);
  const scriptData = useAppStore((s) => s.scriptData);
  const timings = useAppStore((s) => s.timings);
  const setActiveTranscriptIndex = useAppStore((s) => s.setActiveTranscriptIndex);
  const sessionId = useAppStore((s) => s.sessionId);

  const audioUrl = fullAudioUrl || previewAudioUrl;

  // Create / update audio element when URL changes
  useEffect(() => {
    if (!audioUrl) return;
    const audio = new Audio(audioUrl);
    audioRef.current = audio;

    const onLoadedMetadata = () => {
      setDuration(audio.duration);
    };
    const onTimeUpdate = () => {
      const t = audio.currentTime;
      setCurrentTime(t);
      // Update transcript highlight
      if (timings.length) {
        const idx = timings.findIndex(
          (tm) => t >= tm.start && t < tm.end
        );
        if (idx >= 0) {
          setActiveTranscriptIndex(idx);
        }
      }
      // Report playback progress every 10s
      if (sessionId && t - lastReportRef.current >= 10) {
        lastReportRef.current = t;
        addHistory({
          session_id: sessionId,
          progress: Math.floor(t),
          duration: Math.floor(audio.duration || 0),
        }).catch(() => {});
      }
    };
    const onEnded = () => {
      setIsPlaying(false);
    };

    audio.addEventListener("loadedmetadata", onLoadedMetadata);
    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("ended", onEnded);

    // If we had a previous audio, try to preserve time
    return () => {
      audio.pause();
      audio.removeEventListener("loadedmetadata", onLoadedMetadata);
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("ended", onEnded);
      audioRef.current = null;
    };
  }, [audioUrl, timings, setDuration, setCurrentTime, setIsPlaying, setActiveTranscriptIndex, sessionId]);

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
    } else {
      audio.play().catch(() => {});
      setIsPlaying(true);
    }
  }, [isPlaying, setIsPlaying]);

  const seek = useCallback(
    (time) => {
      const audio = audioRef.current;
      if (!audio) return;
      const t = Math.max(0, Math.min(time, audio.duration || 0));
      audio.currentTime = t;
      setCurrentTime(t);
    },
    [setCurrentTime]
  );

  const seekRelative = useCallback(
    (delta) => {
      const audio = audioRef.current;
      if (!audio) return;
      seek((audio.currentTime || 0) + delta);
    },
    [seek]
  );

  return { togglePlay, seek, seekRelative, audioRef };
}
