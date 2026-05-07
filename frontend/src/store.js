import { create } from "zustand";

export const useAppStore = create((set, get) => ({
  // Navigation
  currentPage: "home",
  setPage: (page) => set({ currentPage: page }),

  // Generation state
  sessionId: null,
  setSessionId: (id) => set({ sessionId: id }),
  generationProgress: 0,
  setGenerationProgress: (p) => set({ generationProgress: p }),
  generationStatus: "idle", // idle | generating | complete | failed
  setGenerationStatus: (s) => set({ generationStatus: s }),
  statusText: "",
  setStatusText: (t) => set({ statusText: t }),
  previewAudioUrl: null,
  setPreviewAudioUrl: (url) => set({ previewAudioUrl: url }),
  fullAudioUrl: null,
  setFullAudioUrl: (url) => set({ fullAudioUrl: url }),

  // Player state
  isPlaying: false,
  setIsPlaying: (v) => set({ isPlaying: v }),
  currentTime: 0,
  setCurrentTime: (t) => set({ currentTime: t }),
  duration: 0,
  setDuration: (d) => set({ duration: d }),
  activeTranscriptIndex: -1,
  setActiveTranscriptIndex: (i) => set({ activeTranscriptIndex: i }),

  // Podcast data
  currentPodcast: null,
  setCurrentPodcast: (p) => set({ currentPodcast: p }),
  scriptData: null,
  setScriptData: (d) => set({ scriptData: d }),
  timings: [],
  setTimings: (t) => set({ timings: t }),

  // User preferences
  selectedModel: "kimi",
  setSelectedModel: (m) => set({ selectedModel: m }),
  selectedDuration: "standard",
  setSelectedDuration: (d) => set({ selectedDuration: d }),
  highQuality: true,
  setHighQuality: (v) => set({ highQuality: v }),
  bgMusic: false,
  setBgMusic: (v) => set({ bgMusic: v }),

  // User
  userName: "旅行者",
  setUserName: (n) => set({ userName: n }),
  genCount: 0,
  setGenCount: (c) => set({ genCount: c }),
}));
