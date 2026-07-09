import { clearAuthCookie } from "@/lib/session";

export async function POST() {
  await clearAuthCookie();
  return Response.json({ ok: true });
}
