import { AppShell } from "@/components/layout/app-shell";
import { FormSkeleton } from "@/components/shared/route-skeleton";

export default function NewStoryLoading() {
  return (
    <AppShell title="إنشاء قصة">
      <FormSkeleton />
    </AppShell>
  );
}
