import { useEffect } from "react";
import { useAppStore } from "../store";
import { X, AlertCircle, CheckCircle, Info } from "lucide-react";

const icons = {
  error: AlertCircle,
  success: CheckCircle,
  info: Info,
};

const colors = {
  error: "bg-red-500/10 border-red-500/20 text-red-400",
  success: "bg-brand-tertiary/10 border-brand-tertiary/20 text-brand-tertiary",
  info: "bg-brand-pink/10 border-brand-pink/20 text-brand-pink",
};

export default function Toast() {
  const toast = useAppStore((s) => s.toast);
  const clearToast = useAppStore((s) => s.clearToast);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => clearToast(), 3000);
    return () => clearTimeout(t);
  }, [toast, clearToast]);

  if (!toast) return null;

  const Icon = icons[toast.type] || Info;

  return (
    <div className="fixed top-6 left-1/2 -translate-x-1/2 z-[100] animate-in fade-in slide-in-from-top-2 duration-200">
      <div
        className={`flex items-center gap-3 px-4 py-3 rounded-xl border backdrop-blur-sm shadow-lg ${
          colors[toast.type] || colors.info
        }`}
      >
        <Icon size={16} className="flex-shrink-0" />
        <span className="text-sm font-medium">{toast.message}</span>
        <button
          onClick={clearToast}
          className="p-1 rounded hover:bg-white/10 transition-colors flex-shrink-0"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
