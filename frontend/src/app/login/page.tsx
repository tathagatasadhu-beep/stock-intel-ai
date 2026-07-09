"use client";

import { Lock, Mail, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import IconInput from "@/components/IconInput";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    setSubmitting(false);
    if (!res.ok) {
      setError(data.error || "Login failed.");
      return;
    }
    router.push("/alerts");
    router.refresh();
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-24">
      <Link href="/" className="mb-6 flex items-center gap-2 text-text-muted hover:text-text">
        <TrendingUp className="h-5 w-5 text-accent" />
        <span className="font-semibold">Stock Intelligence</span>
      </Link>
      <div className="w-full max-w-sm rounded-2xl border border-border bg-panel p-8">
        <h1 className="mb-1 text-xl font-bold text-text">Welcome back</h1>
        <p className="mb-6 text-sm text-text-muted">Log in to manage your alerts.</p>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <IconInput icon={Mail} type="email" required placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <IconInput icon={Lock} type="password" required placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
          {error && <p className="text-sm text-bear">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="mt-2 rounded-lg bg-accent py-2.5 font-semibold text-white transition hover:bg-accent-dim disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Logging in..." : "Log In"}
          </button>
        </form>
        <p className="mt-5 text-center text-sm text-text-muted">
          New here?{" "}
          <Link href="/signup" className="font-medium text-accent hover:underline">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}
