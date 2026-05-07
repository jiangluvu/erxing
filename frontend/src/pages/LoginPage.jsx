import { useState } from "react";
import { Mail, Lock, Globe } from "lucide-react";
import { useAppStore } from "../store";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const setPage = useAppStore((s) => s.setPage);

  const handleLogin = (e) => {
    e.preventDefault();
    setLoading(true);
    // Simulate login
    setTimeout(() => {
      setLoading(false);
      setPage("home");
    }, 800);
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-10">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="text-3xl font-black text-brand-pink mb-2">耳行</div>
          <p className="text-sm text-slate-500">登录以同步你的播客与收藏</p>
        </div>

        {/* Form */}
        <form
          onSubmit={handleLogin}
          className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-6 mb-4"
        >
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                邮箱
              </label>
              <div className="flex items-center gap-3 bg-[#1a1a1c] border border-[#2a2a2a] rounded-xl px-4 py-3 focus-within:border-brand-pink/50 transition-colors">
                <Mail size={16} className="text-slate-500" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="your@email.com"
                  className="w-full bg-transparent text-sm text-white placeholder-slate-600 outline-none"
                  required
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                密码
              </label>
              <div className="flex items-center gap-3 bg-[#1a1a1c] border border-[#2a2a2a] rounded-xl px-4 py-3 focus-within:border-brand-pink/50 transition-colors">
                <Lock size={16} className="text-slate-500" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="输入密码"
                  className="w-full bg-transparent text-sm text-white placeholder-slate-600 outline-none"
                  required
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-white text-black rounded-xl text-sm font-bold hover:bg-white/90 transition-all disabled:opacity-50"
            >
              {loading ? "登录中…" : "登录"}
            </button>
          </div>

          <div className="flex items-center gap-3 my-4">
            <div className="flex-1 h-px bg-[#2a2a2a]" />
            <span className="text-xs text-slate-500">或</span>
            <div className="flex-1 h-px bg-[#2a2a2a]" />
          </div>

          <button
            type="button"
            className="w-full flex items-center justify-center gap-2 py-3 bg-white/5 border border-white/5 rounded-xl text-sm text-white hover:bg-white/10 transition-all"
          >
            <Globe size={16} />
            <span>使用 GitHub 登录</span>
          </button>
        </form>

        {/* Toggle */}
        <div className="text-center text-xs text-slate-500">
          还没有账号？
          <button className="text-brand-pink hover:underline ml-1">立即注册</button>
        </div>
      </div>
    </div>
  );
}
