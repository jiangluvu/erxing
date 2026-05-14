import { useEffect } from "react";
import { useAppStore } from "./store";
import SideNavBar from "./components/SideNavBar";
import Toast from "./components/Toast";
import { getPodcasts } from "./api";
import ZeroStatePage from "./pages/ZeroStatePage";
import MyPodcastsPage from "./pages/MyPodcastsPage";
import GenerationPage from "./pages/GenerationPage";
import PlayerPage from "./pages/PlayerPage";
import DetailPage from "./pages/DetailPage";
import SettingsPage from "./pages/SettingsPage";
import SubscriptionPage from "./pages/SubscriptionPage";
import SearchPage from "./pages/SearchPage";
import HotPage from "./pages/HotPage";
import CollectionsPage from "./pages/CollectionsPage";
import HistoryPage from "./pages/HistoryPage";
import FavoritesPage from "./pages/FavoritesPage";
import NotesPage from "./pages/NotesPage";
import LoginPage from "./pages/LoginPage";
import ScriptEditorPage from "./pages/ScriptEditorPage";
import MyVoicesPage from "./pages/MyVoicesPage";

const pages = {
  home: ZeroStatePage,
  myPodcasts: MyPodcastsPage,
  generation: GenerationPage,
  player: PlayerPage,
  detail: DetailPage,
  settings: SettingsPage,
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
};

export default function App() {
  const currentPage = useAppStore((s) => s.currentPage);
  const setGenCount = useAppStore((s) => s.setGenCount);
  const Page = pages[currentPage] || ZeroStatePage;

  useEffect(() => {
    getPodcasts()
      .then((data) => {
        const count = data?.podcasts?.length || 0;
        setGenCount(count);
      })
      .catch(() => {});
  }, [setGenCount]);

  return (
    <div className="flex min-h-screen">
      <SideNavBar />
      <main className="ml-[240px] flex-1">
        <Page />
      </main>
      <Toast />
    </div>
  );
}
