import { useAppStore } from "../store";
import { ArrowRight } from "lucide-react";

export default function PersistentNotif() {
  const notif = useAppStore((s) => s.persistentNotif);
  const clear = useAppStore((s) => s.clearPersistentNotif);
  const setPage = useAppStore((s) => s.setPage);

  if (!notif) return null;

  return (
    <div className="fixed bottom-6 left-6 z-50 max-w-sm">
      <div
        onClick={() => {
          if (notif.actionPage) setPage(notif.actionPage);
          clear();
        }}
        className="flex items-center gap-3 px-5 py-3.5 bg-white text-black rounded-2xl shadow-2xl cursor-pointer hover:bg-white/90 transition-all active:scale-95"
      >
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold truncate">{notif.message}</p>
          {notif.actionLabel && (
            <p className="text-xs text-slate-500 mt-0.5">{notif.actionLabel}</p>
          )}
        </div>
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-black/5 flex items-center justify-center">
          <ArrowRight size={16} />
        </div>
      </div>
    </div>
  );
}