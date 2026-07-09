import { BackendError, backendFetch } from "@/lib/api";
import { getAuthToken } from "@/lib/session";

export async function GET() {
  const token = await getAuthToken();
  if (!token) return Response.json({ error: "Not signed in." }, { status: 401 });
  try {
    const alerts = await backendFetch("/api/alerts", { headers: { Authorization: `Bearer ${token}` } });
    return Response.json(alerts);
  } catch (err) {
    const status = err instanceof BackendError ? err.status : 500;
    return Response.json({ error: "Failed to load alerts." }, { status });
  }
}

export async function POST(req: Request) {
  const token = await getAuthToken();
  if (!token) return Response.json({ error: "Not signed in." }, { status: 401 });
  const body = await req.json();
  try {
    const alert = await backendFetch("/api/alerts", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    });
    return Response.json(alert, { status: 201 });
  } catch (err) {
    const status = err instanceof BackendError ? err.status : 500;
    const message = err instanceof BackendError ? err.message : "Failed to create alert.";
    return Response.json({ error: message }, { status });
  }
}
