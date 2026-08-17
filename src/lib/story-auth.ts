import "server-only";
import { requireUser } from "@/server/auth/session";

export async function requireStoryUserId(): Promise<string> {
  const user = await requireUser();
  return user.id;
}
