import { BackendError, backendFetch } from "@/lib/api";
import { getAuthToken } from "@/lib/session";

export async function DELETE(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const token = await getAuthToken();
  if (!token) return Response.json({ error: "Not signed in." }, { status: 401 });
  const { id } = await params;
  try {
    await backendFetch(`/api/alerts/${id}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
    return new Response(null, { status: 204 });
  } catch (err) {
    const status = err instanceof BackendError ? err.status : 500;
    return Response.json({ error: "Failed to delete alert." }, { status });
  }
}
