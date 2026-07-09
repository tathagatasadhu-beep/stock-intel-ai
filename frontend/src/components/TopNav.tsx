"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { TrendingUp, Search } from "lucide-react";

export function TopNav() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const ticker = query.trim().toUpperCase();
    if (ticker) {
      router.push(`/stock/${ticker}`);
      setQuery("");
    }
  }

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-panel/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1600px] items-center gap-6 px-4 py-3">
        <Link href="/" className="flex items-center gap-2 font-semibold text-text">
          <TrendingUp className="h-5 w-5 text-accent" />
          <span className="hidden sm:inline">Stock Intelligence</span>
        </Link>

        <nav className="flex items-center gap-4 text-sm text-text-muted">
          <Link href="/" className="hover:text-text">
            Screener
          </Link>
          <Link href="/alerts" className="hover:text-text">
            Alerts
          </Link>
        </nav>

        <form onSubmit={handleSubmit} className="ml-auto flex max-w-xs flex-1 items-center gap-2 rounded-md border border-border bg-panel-2 px-3 py-1.5">
          <Search className="h-4 w-4 text-text-faint" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search ticker (e.g. AAPL)"
            className="w-full bg-transparent text-sm text-text placeholder:text-text-faint focus:outline-none"
          />
        </form>
      </div>
    </header>
  );
}
