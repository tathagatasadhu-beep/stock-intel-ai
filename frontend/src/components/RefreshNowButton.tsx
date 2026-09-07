"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";

export function RefreshNowButton({ ticker }: { ticker: string }) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setState("loading");
    setError(null);
    try {
      const res = await fetch(`/api/stocks/${ticker}/refresh`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Failed to fetch live data for this stock.");
        setState("error");
        return;
      }
      // Re-render the (Server Component) page now that the backend has real data for
      // this ticker — no client-side state to reconcile, just ask Next.js for a fresh
      // render. Normally this button unmounts entirely once the page switches to the
      // full stock view; resetting to idle is just a fallback in case it doesn't.
      router.refresh();
      setState("idle");
    } catch {
      setError("Network error — try again.");
      setState("error");
    }
  }

  return (
    <div className="mt-6 flex flex-col items-center gap-2">
      <button
        onClick={handleClick}
        disabled={state === "loading"}
        className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-dim disabled:cursor-not-allowed disabled:opacity-60"
      >
        {state === "loading" ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Fetching live data — this takes a few seconds...
          </>
        ) : (
          <>
            <RefreshCw className="h-4 w-4" />
            Fetch {ticker} now
          </>
        )}
      </button>
      {error && <p className="text-sm text-bear">{error}</p>}
    </div>
  );
}
