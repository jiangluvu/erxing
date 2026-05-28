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
  const timings = useAppStore((s) => s.timings);
  const setActiveTranscriptIndex = useAppStore((s) => s.setActiveTranscriptIndex);
  const sessionId = useAppStore((s) => s.sessionId);
  const currentTime = useAppStore((s) => s.currentTime);

  const audioUrl = fullAudioUrl || previewAudioUrl;

  // Use refs to read latest store values without triggering audio recreation
  const timingsRef = useRef(timings);
  timingsRef.current = timings;
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;
  const isPlayingRef = useRef(isPlaying);
  isPlayingRef.current = isPlaying;
  const currentTimeRef = useRef(currentTime);
  currentTimeRef.current = currentTime;

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
      // Update transcript highlight using ref (no dependency needed)
      const tm = timingsRef.current;
      let idx = -1;
      if (tm.length) {
        idx = tm.findIndex(
          (item) => t >= item.start && t < item.end
        );
        if (idx >= 0) {
          setActiveTranscriptIndex(idx);
        }
      }
      // Turn-level playback tracking
      const sid = sessionIdRef.current;
      if (sid && idx >= 0 && idx !== lastTurnIndexRef.current) {
        // Exit previous turn
        if (lastTurnIndexRef.current >= 0 && turnEnterRef.current) {
          reportPlaybackEvent({
            session_id: sid,
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
          session_id: sid,
          turn_index: idx,
          event_type: "turn_start",
          total_listen_time_s: Math.floor(t),
        }).catch(() => {});
      }
      // Report playback progress every 10s
      if (sid && t - lastReportRef.current >= 10) {
        lastReportRef.current = t;
        addHistory({
          session_id: sid,
          progress: Math.floor(t),
          duration: Math.floor(audio.duration || 0),
        }).catch(() => {});
      }
    };
    const onEnded = () => {
      setIsPlaying(false);
      const sid = sessionIdRef.current;
      if (sid && lastTurnIndexRef.current >= 0 && turnEnterRef.current) {
        reportPlaybackEvent({
          session_id: sid,
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
      const sid = sessionIdRef.current;
      const ct = currentTimeRef.current;
      if (sid && lastTurnIndexRef.current >= 0 && turnEnterRef.current) {
        reportPlaybackEvent({
          session_id: sid,
          turn_index: lastTurnIndexRef.current,
          event_type: "exit",
          listen_duration_s: Math.round((Date.now() - turnEnterRef.current) / 100 * 10) / 10,
          total_listen_time_s: Math.floor(ct),
        }).catch(() => {});
      }
    };

    audio.addEventListener("loadedmetadata", onLoadedMetadata);
    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("ended", onEnded);
    window.addEventListener("beforeunload", onBeforeUnload);

    return () => {
      audio.pause();
      audio.removeEventListener("loadedmetadata", onLoadedMetadata);
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("ended", onEnded);
      window.removeEventListener("beforeunload", onBeforeUnload);
      audioRef.current = null;
    };
    // Only recreate audio when the URL changes — NOT on timings/sessionId changes
  }, [audioUrl]); // eslint-disable-line react-hooks/exhaustive-deps

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
