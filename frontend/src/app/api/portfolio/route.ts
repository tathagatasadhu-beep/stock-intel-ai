import { BackendError, backendFetch } from "@/lib/api";
import { getAuthToken } from "@/lib/session";

// Adding a holding triggers a best-effort immediate ingestion on the backend (same
// pipeline as POST /api/stocks/{ticker}/refresh) — can take longer than a serverless
// function's default ~10s timeout.
export const maxDuration = 60;

export async function GET() {
  const token = await getAuthToken();
  if (!token) return Response.json({ error: "Not signed in." }, { status: 401 });
  try {
    const portfolio = await backendFetch("/api/portfolio", { headers: { Authorization: `Bearer ${token}` } });
    return Response.json(portfolio);
  } catch (err) {
    const status = err instanceof BackendError ? err.status : 500;
    return Response.json({ error: "Failed to load portfolio." }, { status });
  }
}

export async function POST(req: Request) {
  const token = await getAuthToken();
  if (!token) return Response.json({ error: "Not signed in." }, { status: 401 });
  const body = await req.json();
  try {
    const holding = await backendFetch("/api/portfolio/holdings", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    });
    return Response.json(holding, { status: 201 });
  } catch (err) {
    const status = err instanceof BackendError ? err.status : 500;
    const message = err instanceof BackendError ? err.message : "Failed to add holding.";
    return Response.json({ error: message }, { status });
  }
}
