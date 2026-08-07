import { AppShell } from "@/components/layout/app-shell";
import { SectionTitle } from "@/components/ui/card";
import { requireUser } from "@/server/auth/session";
import { ProfileForm } from "@/components/auth/profile-form";

export default async function ProfilePage() {
  const user = await requireUser();
  return (
    <AppShell title="الملف الشخصي">
      <div className="space-y-6">
        <SectionTitle title="الملف الشخصي" subtitle="بيانات الحساب الأكاديمي المستخدمة لتخصيص تجربة إنشاء القصص." />
        <ProfileForm user={user} />
      </div>
    </AppShell>
  );
}
