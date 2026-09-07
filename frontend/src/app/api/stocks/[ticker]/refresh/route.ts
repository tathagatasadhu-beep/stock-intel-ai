import { BackendError, backendFetch } from "@/lib/api";

// The backend ingestion pipeline (several sequential FMP calls + an OpenAI call) can
// take longer than a serverless function's default ~10s timeout — this asks Vercel for
// more headroom. If the account tier caps it lower, the request just fails faster than
// this; the frontend's RefreshNowButton already shows its own error either way.
export const maxDuration = 60;

export async function POST(_req: Request, { params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;
  try {
    const result = await backendFetch<{ status: string; ticker: string }>(`/api/stocks/${ticker}/refresh`, { method: "POST" });
    return Response.json(result);
  } catch (err) {
    const status = err instanceof BackendError ? err.status : 500;
    const message = err instanceof BackendError ? err.message : "Failed to refresh this stock.";
    return Response.json({ error: message }, { status });
  }
}
