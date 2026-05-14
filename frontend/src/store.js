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

  // Voice config
  maleVoiceId: "639cdf5253a24b50a18cbdb726acce15",
  setMaleVoiceId: (id) => set({ maleVoiceId: id }),
  femaleVoiceId: "a71b052094fa4505967e262b8cb7d0a6",
  setFemaleVoiceId: (id) => set({ femaleVoiceId: id }),
  defaultEmotion: "正常",
  setDefaultEmotion: (e) => set({ defaultEmotion: e }),

  // Custom voices / emotions (persisted via localStorage)
  customMaleVoices: JSON.parse(
    typeof window !== "undefined"
      ? localStorage.getItem("boke_custom_male_voices") || "[]"
      : "[]"
  ),
  addCustomMaleVoice: (v) =>
    set((state) => {
      const next = [...state.customMaleVoices, v];
      localStorage.setItem("boke_custom_male_voices", JSON.stringify(next));
      return { customMaleVoices: next };
    }),
  removeCustomMaleVoice: (id) =>
    set((state) => {
      const next = state.customMaleVoices.filter((v) => v.id !== id);
      localStorage.setItem("boke_custom_male_voices", JSON.stringify(next));
      return { customMaleVoices: next };
    }),
  customFemaleVoices: JSON.parse(
    typeof window !== "undefined"
      ? localStorage.getItem("boke_custom_female_voices") || "[]"
      : "[]"
  ),
  addCustomFemaleVoice: (v) =>
    set((state) => {
      const next = [...state.customFemaleVoices, v];
      localStorage.setItem("boke_custom_female_voices", JSON.stringify(next));
      return { customFemaleVoices: next };
    }),
  removeCustomFemaleVoice: (id) =>
    set((state) => {
      const next = state.customFemaleVoices.filter((v) => v.id !== id);
      localStorage.setItem("boke_custom_female_voices", JSON.stringify(next));
      return { customFemaleVoices: next };
    }),
  customEmotions: JSON.parse(
    typeof window !== "undefined"
      ? localStorage.getItem("boke_custom_emotions") || "[]"
      : "[]"
  ),
  addCustomEmotion: (e) =>
    set((state) => {
      const next = [...state.customEmotions, e];
      localStorage.setItem("boke_custom_emotions", JSON.stringify(next));
      return { customEmotions: next };
    }),
  removeCustomEmotion: (value) =>
    set((state) => {
      const next = state.customEmotions.filter((e) => e.value !== value);
      localStorage.setItem("boke_custom_emotions", JSON.stringify(next));
      return { customEmotions: next };
    }),

  // Global podcast settings (intro / outro / body bgm)
  podcastSettings: JSON.parse(
    typeof window !== "undefined"
      ? localStorage.getItem("boke_podcast_settings") || "null"
      : "null"
  ),
  setPodcastSettings: (updater) =>
    set((state) => {
      const next =
        typeof updater === "function"
          ? updater(state.podcastSettings || {})
          : { ...(state.podcastSettings || {}), ...updater };
      localStorage.setItem("boke_podcast_settings", JSON.stringify(next));
      return { podcastSettings: next };
    }),

  // User
  userName: "旅行者",
  setUserName: (n) => set({ userName: n }),
  genCount: 0,
  setGenCount: (updater) =>
    set((state) => ({
      genCount:
        typeof updater === "function" ? updater(state.genCount) : updater,
    })),

  // Toast
  toast: null,
  showToast: (message, type = "info") => set({ toast: { message, type } }),
  clearToast: () => set({ toast: null }),
}));
