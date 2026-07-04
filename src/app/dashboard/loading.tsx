import { AppShell } from "@/components/layout/app-shell";
import { RouteSkeleton } from "@/components/shared/route-skeleton";

export default function DashboardLoading() {
  return (
    <AppShell title="لوحة التحكم">
      <RouteSkeleton />
    </AppShell>
  );
}
