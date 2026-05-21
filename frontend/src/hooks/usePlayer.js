import { useCallback, useEffect, useRef } from "react";
import { useAppStore } from "../store";
import { addHistory, reportPlaybackEvent } from "../api";

export function usePlayer() {
  const audioRef = useRef(null);
  const lastReportRef = useRef(0);
  const turnEnterRef = useRef(null);
  const lastTurnIndexRef = useRef(-1);

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
  const currentTime = useAppStore((s) => s.currentTime);

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
      let idx = -1;
      if (timings.length) {
        idx = timings.findIndex(
          (tm) => t >= tm.start && t < tm.end
        );
        if (idx >= 0) {
          setActiveTranscriptIndex(idx);
        }
      }
      // Turn-level playback tracking
      if (sessionId && idx >= 0 && idx !== lastTurnIndexRef.current) {
        // Exit previous turn
        if (lastTurnIndexRef.current >= 0 && turnEnterRef.current) {
          reportPlaybackEvent({
            session_id: sessionId,
            turn_index: lastTurnIndexRef.current,
            event_type: "turn_exit",
            listen_duration_s: Math.round((Date.now() - turnEnterRef.current) / 100 * 10) / 10,
            total_listen_time_s: Math.floor(t),
          }).catch(() => {});
        }
        // Enter new turn
        lastTurnIndexRef.current = idx;
        turnEnterRef.current = Date.now();
        reportPlaybackEvent({
          session_id: sessionId,
          turn_index: idx,
          event_type: "turn_start",
          total_listen_time_s: Math.floor(t),
        }).catch(() => {});
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
      if (sessionId && lastTurnIndexRef.current >= 0 && turnEnterRef.current) {
        reportPlaybackEvent({
          session_id: sessionId,
          turn_index: lastTurnIndexRef.current,
          event_type: "turn_exit",
          listen_duration_s: Math.round((Date.now() - turnEnterRef.current) / 100 * 10) / 10,
          total_listen_time_s: Math.floor(audio.currentTime || 0),
        }).catch(() => {});
        lastTurnIndexRef.current = -1;
        turnEnterRef.current = null;
      }
    };

    const onBeforeUnload = () => {
      if (sessionId && lastTurnIndexRef.current >= 0 && turnEnterRef.current) {
        reportPlaybackEvent({
          session_id: sessionId,
          turn_index: lastTurnIndexRef.current,
          event_type: "exit",
          listen_duration_s: Math.round((Date.now() - turnEnterRef.current) / 100 * 10) / 10,
          total_listen_time_s: Math.floor(currentTime),
        }).catch(() => {});
      }
    };

    audio.addEventListener("loadedmetadata", onLoadedMetadata);
    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("ended", onEnded);
    window.addEventListener("beforeunload", onBeforeUnload);

    // If we had a previous audio, try to preserve time
    return () => {
      audio.pause();
      audio.removeEventListener("loadedmetadata", onLoadedMetadata);
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("ended", onEnded);
      window.removeEventListener("beforeunload", onBeforeUnload);
      audioRef.current = null;
    };
  }, [audioUrl, timings, setDuration, setCurrentTime, setIsPlaying, setActiveTranscriptIndex, sessionId, currentTime]);

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
