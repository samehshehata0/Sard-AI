import { getCurrentUser } from "@/server/auth/session";

export async function SidebarUserChip() {
  const user = await getCurrentUser();
  if (!user) return null;

  return (
    <div className="mt-6 truncate rounded-2xl border border-border bg-card px-4 py-3 text-xs font-bold text-muted-foreground" title={user.email}>
      {user.email}
    </div>
  );
}
