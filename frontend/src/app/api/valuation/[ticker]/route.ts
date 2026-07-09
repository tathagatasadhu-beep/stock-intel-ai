import { BackendError, backendFetch, ValuationOut } from "@/lib/api";

export async function GET(req: Request, { params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;
  const { search } = new URL(req.url);
  try {
    const result = await backendFetch<ValuationOut>(`/api/valuation/${ticker}${search}`);
    return Response.json(result);
  } catch (err) {
    const status = err instanceof BackendError ? err.status : 500;
    const message = err instanceof BackendError ? err.message : "Failed to compute valuation.";
    return Response.json({ error: message }, { status });
  }
}
