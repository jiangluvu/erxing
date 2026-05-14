import { useEffect } from "react";
import { useAppStore } from "../store";
import { useGeneration } from "../hooks/useGeneration";
import {
  CheckCircle2,
  Loader2,
  Circle,
  ArrowLeft,
  X,
  User,
} from "lucide-react";

const steps = [
  { label: "解析文章内容" },
  { label: "提取核心观点" },
  { label: "构建对谈大纲" },
  { label: "生成对话脚本" },
  { label: "语音合成" },
  { label: "音频增强" },
];

export default function GenerationPage() {
  const generationProgress = useAppStore((s) => s.generationProgress);
  const generationStatus = useAppStore((s) => s.generationStatus);
  const statusText = useAppStore((s) => s.statusText);
  const setPage = useAppStore((s) => s.setPage);
  const { cancelGeneration } = useGeneration();

  useEffect(() => {
    if (generationStatus === "complete") {
      setPage("player");
    }
  }, [generationStatus, setPage]);

  const completedSteps = Math.floor((generationProgress / 100) * steps.length);

  const handleCancel = () => {
    cancelGeneration();
    setPage("home");
  };

  const handleBack = () => {
    setPage("home");
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-10">
      <div className="w-full max-w-lg">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <button
            onClick={handleBack}
            className="p-2 rounded-lg hover:bg-white/5 text-slate-400 hover:text-white transition-all"
          >
            <ArrowLeft size={18} />
          </button>
          <button
            onClick={handleCancel}
            className="p-2 rounded-lg hover:bg-white/5 text-slate-400 hover:text-red-400 transition-all"
          >
            <X size={18} />
          </button>
        </div>

        {/* Avatars */}
        <div className="flex items-center justify-center gap-12 mb-10">
          <div className="text-center">
            <div className="relative w-20 h-20 mx-auto mb-3">
              <div className="w-20 h-20 rounded-full bg-brand-pink/10 flex items-center justify-center text-brand-pink">
                <User size={32} />
              </div>
            </div>
            <div className="text-sm font-semibold text-white">男声</div>
          </div>
          <div className="text-center">
            <div className="relative w-20 h-20 mx-auto mb-3">
              <div className="w-20 h-20 rounded-full bg-white/5 flex items-center justify-center text-slate-400">
                <User size={32} />
              </div>
            </div>
            <div className="text-sm font-semibold text-white">女声</div>
          </div>
        </div>

        {/* Progress Card */}
        <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-semibold text-white">
              {statusText || "准备中..."}
            </span>
            <span className="text-sm font-bold text-brand-pink">
              {generationProgress}%
            </span>
          </div>
          <div className="h-2 bg-white/5 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-brand-pink to-brand-tertiary transition-all duration-500"
              style={{ width: `${generationProgress}%` }}
            />
          </div>
        </div>

        {/* Steps */}
        <div className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-6">
          <div className="space-y-3">
            {steps.map((step, i) => {
              const isCompleted = i < completedSteps;
              const isCurrent =
                i === completedSteps && generationStatus === "generating";
              return (
                <div key={step.label} className="flex items-center gap-3">
                  {isCompleted ? (
                    <CheckCircle2
                      size={18}
                      className="text-brand-tertiary flex-shrink-0"
                    />
                  ) : isCurrent ? (
                    <Loader2
                      size={18}
                      className="text-brand-pink animate-spin flex-shrink-0"
                    />
                  ) : (
                    <Circle
                      size={18}
                      className="text-slate-700 flex-shrink-0"
                    />
                  )}
                  <span
                    className={`text-sm ${
                      isCompleted
                        ? "text-brand-tertiary"
                        : isCurrent
                        ? "text-white"
                        : "text-slate-600"
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
