import { AppShell } from "@/components/layout/app-shell";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { Card, SectionTitle } from "@/components/ui/card";
import { requireUser } from "@/server/auth/session";
import { AvatarSection } from "@/components/settings/avatar-section";
import { PersonalInfoSection } from "@/components/settings/personal-info-section";
import { RoleInstitutionSection } from "@/components/settings/role-institution-section";

export default async function SettingsPage() {
  const user = await requireUser();

  return (
    <AppShell title="الإعدادات">
      <div className="space-y-6">
        <SectionTitle title="الإعدادات" subtitle="اضبط المظهر وبيانات الحساب الأكاديمي." />

        <SectionTitle title="الملف الشخصي" subtitle="بيانات الحساب الأكاديمي المستخدمة لتخصيص تجربة إنشاء القصص." />
        <div className="space-y-6">
          <AvatarSection user={user} />
          <PersonalInfoSection user={user} />
          <RoleInstitutionSection user={user} />
        </div>

        <Card>
          <h3 className="font-heading text-xl font-extrabold text-foreground">المظهر</h3>
          <div className="mt-5">
            <ThemeToggle />
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
