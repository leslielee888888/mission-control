import { useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { Spinner } from "../components/Spinner";

function Logo() {
  return (
    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="1.75">
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="2.5" fill="var(--color-accent)" stroke="none" />
      <path d="M12 3 a9 4 0 0 1 0 18 a9 4 0 0 1 0 -18" transform="rotate(35 12 12)" />
    </svg>
  );
}

export function LoginScreen() {
  const { login, isLoggingIn, loginError } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    try {
      await login(email, password);
    } catch {
      // loginError (from AuthContext, sourced off the mutation) renders the message.
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4 py-10">
      <div className="flex w-full max-w-[400px] flex-col gap-7">
        <div className="flex flex-col items-center gap-2.5 text-center">
          <Logo />
          <div className="text-lg font-bold tracking-tight">Mission Control</div>
          <div className="text-[13px] text-text-2">Sign in to your organization</div>
        </div>

        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-[18px] rounded-[10px] border border-border bg-surface p-7 shadow-sm"
        >
          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-xs font-semibold text-text-2">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="jordan.lee@aurora-deepspace.example"
              className="w-full rounded-md border border-border bg-surface px-3 py-2.5 text-sm text-text placeholder:text-text-3 focus:border-accent focus:outline-none"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-xs font-semibold text-text-2">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••"
              className="w-full rounded-md border border-border bg-surface px-3 py-2.5 text-sm text-text placeholder:text-text-3 focus:border-accent focus:outline-none"
            />
          </div>

          {loginError && (
            <div className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-xs text-danger" role="alert">
              {loginError}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoggingIn}
            className="mt-1 flex items-center justify-center gap-2 rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isLoggingIn && <Spinner />}
            {isLoggingIn ? "Signing in…" : "Sign in"}
          </button>
          <div className="text-xs text-text-3">
            Wrong credentials return a plain "email or password is incorrect" — never which one was wrong.
          </div>
        </form>

        <div className="flex items-center gap-2.5 text-[11px] uppercase tracking-wide text-text-3">
          <div className="h-px flex-1 bg-border" />
          <div>same account, other client</div>
          <div className="h-px flex-1 bg-border" />
        </div>

        <div className="flex items-start gap-2.5 rounded-lg border border-border bg-surface-2 px-4 py-3.5">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-2)" strokeWidth="1.75" className="mt-px flex-none">
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d="M7 9l3 3-3 3M13 15h4" />
          </svg>
          <div>
            <div className="font-mono text-[12.5px] text-text">missionctl login &lt;email&gt; &lt;password&gt;</div>
            <div className="mt-0.5 text-xs text-text-3">The CLI uses the exact same login endpoint — one credential, both clients.</div>
          </div>
        </div>
      </div>
    </div>
  );
}
