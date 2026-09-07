"use client";

import { createClient } from "@supabase/supabase-js";
import { AlertCircle, CheckCircle2, Lock, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import IconInput from "@/components/IconInput";

// This page is the one deliberate exception to "the browser never talks to the backend or
// Supabase directly" (see CLAUDE.md -> Conventions): Supabase's password-recovery flow
// requires the browser to hold the recovery session from the emailed link and call
// updateUser() directly — there's no way to proxy that through the httpOnly-cookie BFF
// pattern used everywhere else. The anon key is meant to be public. Mirrors EduQuestAI's
// frontend/src/app/parent/reset-password/page.tsx, same underlying reason.
export default function ResetPasswordPage() {
  const router = useRouter();
  const supabase = useMemo(
    () => createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!),
    []
  );

  const [status, setStatus] = useState<"checking" | "ready" | "invalid" | "done">("checking");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY") setStatus("ready");
    });

    // The recovery link may have already been consumed into a session by the time this
    // effect runs (detectSessionInUrl fires on client construction).
    supabase.auth.getSession().then(({ data }) => {
      setStatus((prev) => (prev === "checking" ? (data.session ? "ready" : "invalid") : prev));
    });

    return () => subscription.unsubscribe();
  }, [supabase]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }
    setSubmitting(true);
    setError(null);
    const { error: updateError } = await supabase.auth.updateUser({ password });
    setSubmitting(false);
    if (updateError) {
      setError(updateError.message);
      return;
    }
    await supabase.auth.signOut();
    setStatus("done");
    setTimeout(() => router.push("/login"), 2000);
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-24">
      <Link href="/" className="mb-6 flex items-center gap-2 text-text-muted hover:text-text">
        <TrendingUp className="h-5 w-5 text-accent" />
        <span className="font-semibold">Stock Intelligence</span>
      </Link>
      <div className="w-full max-w-sm rounded-2xl border border-border bg-panel p-8">
        {status === "checking" && <p className="text-sm text-text-muted">Verifying your reset link…</p>}

        {status === "invalid" && (
          <>
            <div className="mb-2 flex items-center gap-2 text-bear">
              <AlertCircle className="h-5 w-5" strokeWidth={2.2} />
              <h1 className="text-xl font-bold text-text">Link expired or invalid</h1>
            </div>
            <p className="mb-5 text-sm text-text-muted">Request a new password reset link and try again.</p>
            <Link
              href="/forgot-password"
              className="block rounded-lg bg-accent py-2.5 text-center font-semibold text-white transition hover:bg-accent-dim"
            >
              Request a new link
            </Link>
          </>
        )}

        {status === "done" && (
          <>
            <div className="mb-2 flex items-center gap-2 text-bull">
              <CheckCircle2 className="h-5 w-5" strokeWidth={2.2} />
              <h1 className="text-xl font-bold text-text">Password updated</h1>
            </div>
            <p className="text-sm text-text-muted">Taking you to the login page…</p>
          </>
        )}

        {status === "ready" && (
          <>
            <h1 className="mb-1 text-xl font-bold text-text">Choose a new password</h1>
            <p className="mb-6 text-sm text-text-muted">Make it something you haven&apos;t used before.</p>
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <IconInput
                icon={Lock}
                type="password"
                required
                minLength={8}
                placeholder="New password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <IconInput
                icon={Lock}
                type="password"
                required
                minLength={8}
                placeholder="Confirm new password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
              {error && <p className="text-sm text-bear">{error}</p>}
              <button
                type="submit"
                disabled={submitting}
                className="mt-2 rounded-lg bg-accent py-2.5 font-semibold text-white transition hover:bg-accent-dim disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? "Updating..." : "Update password"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
