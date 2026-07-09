import type { Metadata } from "next";
import "./globals.css";
import { TopNav } from "@/components/TopNav";

export const metadata: Metadata = {
  title: {
    default: "Stock Intelligence Platform",
    template: "%s · Stock Intelligence",
  },
  description: "AI-powered S&P 500 screening, valuation, and technical analysis.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-bg text-text">
        <TopNav />
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
