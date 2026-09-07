import { BackendError, backendFetch } from "@/lib/api";

export async function POST(req: Request) {
  const body = await req.json();
  try {
    await backendFetch("/api/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify(body),
    });
    return Response.json({ detail: "If that email is registered, a reset link has been sent." });
  } catch (err) {
    const status = err instanceof BackendError ? err.status : 500;
    const message = err instanceof BackendError ? err.message : "Could not send reset email.";
    return Response.json({ error: message }, { status });
  }
}
