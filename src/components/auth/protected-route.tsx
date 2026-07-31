import { redirect } from "next/navigation";
import { getCurrentUser } from "@/server/auth/session";

export async function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  return children;
}
