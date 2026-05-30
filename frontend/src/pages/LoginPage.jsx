import { useState } from "react";
import { Mail, Lock, Globe, User, Loader2 } from "lucide-react";
import { useAppStore } from "../store";
import { getPodcasts } from "../api";

export default function LoginPage() {
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [phone, setPhone] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const setPage = useAppStore((s) => s.setPage);
  const setUser = useAppStore((s) => s.setUser);
  const setToken = useAppStore((s) => s.setToken);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    // Client-side validation
    if (!/^\d{8,15}$/.test(phone)) {
      setError("请输入正确的手机号（8-15位数字）");
      setLoading(false);
      return;
    }
    if (password.length < 6) {
      setError("密码至少6位");
      setLoading(false);
      return;
    }

    try {
      // Collect anonymous session IDs for merge
      let sessionIds = [];
      try {
        const podcasts = await getPodcasts();
        sessionIds = podcasts.map((p) => p.id).filter(Boolean);
      } catch {
        // If we can't fetch, proceed without merge
      }

      const body = {
        phone,
        password,
        ...(mode === "register" ? { username: username || phone.slice(-4) } : {}),
        session_ids: sessionIds,
      };

      const res = await fetch(`/api/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "操作失败");

      setToken(data.token);
      setUser(data.user);
      setPage("home");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-10">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="text-3xl font-black text-brand-pink mb-2">播刻</div>
          <p className="text-sm text-slate-500">
            {mode === "login" ? "登录以同步你的播客与收藏" : "创建账号，开启播客之旅"}
          </p>
        </div>

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          className="bg-[#161618] border border-[#2a2a2a] rounded-2xl p-6 mb-4"
        >
          {error && (
            <div className="mb-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-400">
              {error}
            </div>
          )}

          <div className="space-y-4">
            {/* Phone */}
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                手机号
              </label>
              <div className="flex items-center gap-3 bg-[#1a1a1c] border border-[#2a2a2a] rounded-xl px-4 py-3 focus-within:border-brand-pink/50 transition-colors">
                <span className="text-xs text-slate-500">+86</span>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))}
                  placeholder="13800138000"
                  className="w-full bg-transparent text-sm text-white placeholder-slate-600 outline-none"
                  required
                  inputMode="numeric"
                  maxLength={15}
                />
              </div>
            </div>

            {/* Username (register only) */}
            {mode === "register" && (
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">
                  昵称
                </label>
                <div className="flex items-center gap-3 bg-[#1a1a1c] border border-[#2a2a2a] rounded-xl px-4 py-3 focus-within:border-brand-pink/50 transition-colors">
                  <User size={16} className="text-slate-500" />
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="你的昵称"
                    className="w-full bg-transparent text-sm text-white placeholder-slate-600 outline-none"
                    maxLength={20}
                  />
                </div>
              </div>
            )}

            {/* Password */}
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
                  placeholder="至少6位"
                  className="w-full bg-transparent text-sm text-white placeholder-slate-600 outline-none"
                  required
                  minLength={6}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-white text-black rounded-xl text-sm font-bold hover:bg-white/90 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  <span>{mode === "login" ? "登录中…" : "注册中…"}</span>
                </>
              ) : (
                <span>{mode === "login" ? "登录" : "注册"}</span>
              )}
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
          {mode === "login" ? (
            <>
              还没有账号？
              <button
                type="button"
                onClick={() => { setMode("register"); setError(null); }}
                className="text-brand-pink hover:underline ml-1"
              >
                立即注册
              </button>
            </>
          ) : (
            <>
              已有账号？
              <button
                type="button"
                onClick={() => { setMode("login"); setError(null); }}
                className="text-brand-pink hover:underline ml-1"
              >
                去登录
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}