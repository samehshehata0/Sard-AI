import { AppShell } from "@/components/layout/app-shell";
import dynamic from "next/dynamic";
import { FormSkeleton } from "@/components/shared/route-skeleton";
import { SectionTitle } from "@/components/ui/card";

const WizardForm = dynamic(() => import("@/components/stories/wizard-form").then((mod) => mod.WizardForm), {
  loading: () => <FormSkeleton />,
});

export default function NewStoryPage() {
  return (
    <AppShell title="إنشاء قصة">
      <div className="space-y-6">
        <SectionTitle title="معالج إنشاء قصة تعليمية" subtitle="أدخل بيانات القصة والأهداف وخصائص المتعلمين، ثم راجع الملخص قبل التوليد." />
        <WizardForm />
      </div>
    </AppShell>
  );
}
