"use client";

import { CheckCircle2, Mail, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import IconInput from "@/components/IconInput";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const res = await fetch("/api/auth/forgot-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    setSubmitting(false);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Could not send reset email.");
      return;
    }
    setSent(true);
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-24">
      <Link href="/" className="mb-6 flex items-center gap-2 text-text-muted hover:text-text">
        <TrendingUp className="h-5 w-5 text-accent" />
        <span className="font-semibold">Stock Intelligence</span>
      </Link>
      <div className="w-full max-w-sm rounded-2xl border border-border bg-panel p-8">
        {sent ? (
          <>
            <div className="mb-2 flex items-center gap-2 text-bull">
              <CheckCircle2 className="h-5 w-5" strokeWidth={2.2} />
              <h1 className="text-xl font-bold text-text">Check your email</h1>
            </div>
            <p className="text-sm text-text-muted">
              If an account exists for <span className="font-medium text-text">{email}</span>, a password reset
              link is on its way.
            </p>
          </>
        ) : (
          <>
            <h1 className="mb-1 text-xl font-bold text-text">Reset your password</h1>
            <p className="mb-6 text-sm text-text-muted">Enter your email and we&apos;ll send you a reset link.</p>
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <IconInput icon={Mail} type="email" required placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
              {error && <p className="text-sm text-bear">{error}</p>}
              <button
                type="submit"
                disabled={submitting}
                className="mt-2 rounded-lg bg-accent py-2.5 font-semibold text-white transition hover:bg-accent-dim disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? "Sending..." : "Send reset link"}
              </button>
            </form>
          </>
        )}
        <p className="mt-5 text-center text-sm text-text-muted">
          <Link href="/login" className="font-medium text-accent hover:underline">
            Back to login
          </Link>
        </p>
      </div>
    </div>
  );
}
