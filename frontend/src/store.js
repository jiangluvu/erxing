import { create } from "zustand";

export const useAppStore = create((set, get) => ({
  // Navigation
  currentPage: "home",
  setPage: (page) => set({ currentPage: page }),

  // Generation state (persisted to localStorage for session recovery)
  sessionId: (typeof window !== "undefined" ? localStorage.getItem("boke_session_id") : null) || null,
  setSessionId: (id) => {
    if (typeof window !== "undefined") {
      if (id) localStorage.setItem("boke_session_id", id);
      else localStorage.removeItem("boke_session_id");
    }
    set({ sessionId: id });
  },
  generationProgress: typeof window !== "undefined" ? Number(localStorage.getItem("boke_gen_progress") || 0) : 0,
  setGenerationProgress: (p) => {
    if (typeof window !== "undefined") localStorage.setItem("boke_gen_progress", String(p));
    set({ generationProgress: p });
  },
  generationStatus: (typeof window !== "undefined" ? localStorage.getItem("boke_gen_status") : null) || "idle",
  setGenerationStatus: (s) => {
    if (typeof window !== "undefined") localStorage.setItem("boke_gen_status", s);
    set({ generationStatus: s });
  },
  statusText: (typeof window !== "undefined" ? localStorage.getItem("boke_gen_statustext") : null) || "",
  setStatusText: (t) => {
    if (typeof window !== "undefined") localStorage.setItem("boke_gen_statustext", t);
    set({ statusText: t });
  },
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
  scriptData: (() => {
    if (typeof window !== "undefined") {
      try {
        const v = localStorage.getItem("boke_script_data");
        return v ? JSON.parse(v) : null;
      } catch { return null; }
    }
    return null;
  })(),
  setScriptData: (d) => {
    if (typeof window !== "undefined") {
      if (d) localStorage.setItem("boke_script_data", JSON.stringify(d));
      else localStorage.removeItem("boke_script_data");
    }
    set({ scriptData: d });
  },
  timings: [],
  setTimings: (t) => set({ timings: t }),

  // User preferences
  selectedModel: "deepseek",
  setSelectedModel: (m) => set({ selectedModel: m }),
  selectedDuration: "free",
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

  // Drafts (auto-saved scripts)
  drafts: JSON.parse(
    typeof window !== "undefined"
      ? localStorage.getItem("boke_drafts") || "[]"
      : "[]"
  ),
  addDraft: (draft) =>
    set((state) => {
      const next = [draft, ...state.drafts];
      localStorage.setItem("boke_drafts", JSON.stringify(next));
      return { drafts: next };
    }),
  updateDraft: (id, updates) =>
    set((state) => {
      const next = state.drafts.map((d) =>
        d.id === id ? { ...d, ...updates, updated_at: Date.now() } : d
      );
      localStorage.setItem("boke_drafts", JSON.stringify(next));
      return { drafts: next };
    }),
  deleteDraft: (id) =>
    set((state) => {
      const next = state.drafts.filter((d) => d.id !== id);
      localStorage.setItem("boke_drafts", JSON.stringify(next));
      return { drafts: next };
    }),
  currentDraftId: null,
  setCurrentDraftId: (id) => set({ currentDraftId: id }),

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

  // Persistent notification (bottom-left, no auto-dismiss)
  persistentNotif: null,
  setPersistentNotif: (n) => set({ persistentNotif: n }),
  clearPersistentNotif: () => set({ persistentNotif: null }),

  // Persisted input text for ZeroStatePage recovery
  savedInputText: (typeof window !== "undefined" ? localStorage.getItem("boke_input_text") : null) || "",
  setSavedInputText: (t) => {
    if (typeof window !== "undefined") localStorage.setItem("boke_input_text", t);
    set({ savedInputText: t });
  },

  // Selected intro/outro presets for current generation
  selectedIntroPresetId: null,
  setSelectedIntroPresetId: (id) => set({ selectedIntroPresetId: id }),
  selectedOutroPresetId: null,
  setSelectedOutroPresetId: (id) => set({ selectedOutroPresetId: id }),

  // Chapter data for timeline player
  chapters: [],
  setChapters: (ch) => set({ chapters: ch }),
}));
