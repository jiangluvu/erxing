import { useCallback, useEffect, useRef } from "react";
import { useAppStore } from "../store";

export function usePlayer() {
  const audioRef = useRef(null);

  const isPlaying = useAppStore((s) => s.isPlaying);
  const setIsPlaying = useAppStore((s) => s.setIsPlaying);
  const setCurrentTime = useAppStore((s) => s.setCurrentTime);
  const setDuration = useAppStore((s) => s.setDuration);
  const previewAudioUrl = useAppStore((s) => s.previewAudioUrl);
  const fullAudioUrl = useAppStore((s) => s.fullAudioUrl);
  const scriptData = useAppStore((s) => s.scriptData);
  const timings = useAppStore((s) => s.timings);
  const setActiveTranscriptIndex = useAppStore((s) => s.setActiveTranscriptIndex);

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
      setCurrentTime(audio.currentTime);
      // Update transcript highlight
      if (timings.length) {
        const idx = timings.findIndex(
          (t) => audio.currentTime >= t.start && audio.currentTime < t.end
        );
        if (idx >= 0) {
          setActiveTranscriptIndex(idx);
        }
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
  }, [audioUrl, timings, setDuration, setCurrentTime, setIsPlaying, setActiveTranscriptIndex]);

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
