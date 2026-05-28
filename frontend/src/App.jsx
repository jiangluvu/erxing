import { useEffect, useRef } from "react";
import { useAppStore } from "./store";
import SideNavBar from "./components/SideNavBar";
import Toast from "./components/Toast";
import PersistentNotif from "./components/PersistentNotif";
import { getPodcasts, getGenerationStatus, downloadPodcast } from "./api";
import ZeroStatePage from "./pages/ZeroStatePage";
import MyPodcastsPage from "./pages/MyPodcastsPage";
import GenerationPage from "./pages/GenerationPage";
import PlayerPage from "./pages/PlayerPage";
import DetailPage from "./pages/DetailPage";
import SettingsPage from "./pages/SettingsPage";
import WorkshopPage from "./pages/WorkshopPage";
import MyTemplatesPage from "./pages/MyTemplatesPage";
import AccountPage from "./pages/AccountPage";
import SubscriptionPage from "./pages/SubscriptionPage";
import SearchPage from "./pages/SearchPage";
import HotPage from "./pages/HotPage";
import CollectionsPage from "./pages/CollectionsPage";
import HistoryPage from "./pages/HistoryPage";
import FavoritesPage from "./pages/FavoritesPage";
import NotesPage from "./pages/NotesPage";
import MyDraftsPage from "./pages/MyDraftsPage";
import LoginPage from "./pages/LoginPage";
import ScriptEditorPage from "./pages/ScriptEditorPage";
import MyVoicesPage from "./pages/MyVoicesPage";
import UsageStatsPage from "./pages/UsageStatsPage";

const pages = {
  home: ZeroStatePage,
  myPodcasts: MyPodcastsPage,
  generation: GenerationPage,
  player: PlayerPage,
  detail: DetailPage,
  settings: SettingsPage,
  workshop: WorkshopPage,
  myTemplates: MyTemplatesPage,
  account: AccountPage,
  subscriptions: SubscriptionPage,
  search: SearchPage,
  hot: HotPage,
  collections: CollectionsPage,
  history: HistoryPage,
  favorites: FavoritesPage,
  notes: NotesPage,
  login: LoginPage,
  scriptEditor: ScriptEditorPage,
  myVoices: MyVoicesPage,
  myDrafts: MyDraftsPage,
  usage: UsageStatsPage,
};

export default function App() {
  const currentPage = useAppStore((s) => s.currentPage);
  const setGenCount = useAppStore((s) => s.setGenCount);
  const Page = pages[currentPage] || ZeroStatePage;

  const sessionId = useAppStore((s) => s.sessionId);
  const generationStatus = useAppStore((s) => s.generationStatus);
  const setGenerationProgress = useAppStore((s) => s.setGenerationProgress);
  const setGenerationStatus = useAppStore((s) => s.setGenerationStatus);
  const setStatusText = useAppStore((s) => s.setStatusText);
  const setScriptData = useAppStore((s) => s.setScriptData);
  const setTimings = useAppStore((s) => s.setTimings);
  const setFullAudioUrl = useAppStore((s) => s.setFullAudioUrl);
  const pollRef = useRef(null);

  useEffect(() => {
    getPodcasts()
      .then((data) => {
        const count = data?.podcasts?.length || 0;
        setGenCount(count);
      })
      .catch(() => {});
  }, [setGenCount]);

  // Session recovery: poll active generation from any page
  useEffect(() => {
    // Clear existing poll on session change
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }

    if (sessionId && generationStatus === "generating") {
      pollRef.current = setInterval(async () => {
        try {
          const data = await getGenerationStatus(sessionId);
          setGenerationProgress(data.progress || 0);

          const statusSteps = [
            [0, "主持正在读文章…"], [15, "嘉宾正在做笔记…"],
            [30, "主持和嘉宾在讨论…"], [50, "嘉宾在划重点…"],
            [70, "主持在做总结…"], [80, "正在合成语音…"],
            [90, "马上就好了…"],
          ];
          for (const [p, t] of statusSteps) {
            if ((data.progress || 0) <= p) {
              setStatusText(t); break;
            }
          }

          if (data.status === "complete") {
            clearInterval(pollRef.current);
            pollRef.current = null;
            setGenerationStatus("complete");
            setStatusText("已就绪");

            if (data.script) {
              setScriptData(data.script);
              let acc = 0;
              const t = data.script.map((item) => {
                const dur = Math.max(1.5, item.text.length / 4);
                const start = acc;
                acc += dur;
                return { start, end: acc };
              });
              setTimings(t);
            }

            try {
              const fullBlob = await downloadPodcast(sessionId);
              setFullAudioUrl(URL.createObjectURL(fullBlob));
            } catch (e) {
              console.warn("Full audio download failed:", e);
            }
          } else if (data.status === "failed") {
            clearInterval(pollRef.current);
            pollRef.current = null;
            setGenerationStatus("failed");
            setStatusText("生成失败");
          }
        } catch (e) {
          console.warn("Session poll error:", e);
        }
      }, 3000);
    }

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [sessionId, generationStatus]);

  return (
    <div className="flex min-h-screen">
      <SideNavBar />
      <main className="ml-[240px] flex-1">
        <Page />
      </main>
      <Toast />
      <PersistentNotif />
    </div>
  );
}
