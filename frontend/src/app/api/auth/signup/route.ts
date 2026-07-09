import { BackendError, backendFetch } from "@/lib/api";
import { setAuthCookie } from "@/lib/session";

export async function POST(req: Request) {
  const body = await req.json();
  try {
    const result = await backendFetch<{ access_token: string; user: { id: string; email: string } }>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify(body),
    });
    await setAuthCookie(result.access_token);
    return Response.json({ user: result.user });
  } catch (err) {
    const status = err instanceof BackendError ? err.status : 500;
    const message = err instanceof BackendError ? err.message : "Signup failed.";
    return Response.json({ error: message }, { status });
  }
}
