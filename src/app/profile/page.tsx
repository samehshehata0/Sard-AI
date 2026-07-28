import { Edit3 } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card, SectionTitle } from "@/components/ui/card";
import { authService } from "@/services/auth-service";

const roleLabels = { student_teacher: "طالب معلم", faculty_member: "عضو هيئة تدريس", supervisor: "مشرف" };

export default async function ProfilePage() {
  const user = await authService.me();
  return (
    <AppShell title="الملف الشخصي">
      <div className="space-y-6">
        <SectionTitle title="الملف الشخصي" subtitle="بيانات الحساب الأكاديمي المستخدمة لتخصيص تجربة إنشاء القصص." />
        <Card>
          <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-4">
              <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-l from-primary to-secondary font-heading text-2xl font-black text-primary-foreground">س</div>
              <div>
                <h2 className="font-heading text-2xl font-black text-foreground">{user.fullName}</h2>
                <p className="mt-1 text-sm font-bold text-muted-foreground">{roleLabels[user.role]}</p>
              </div>
            </div>
            <ArabicButton icon={<Edit3 className="h-4 w-4" />}>تعديل الملف الشخصي</ArabicButton>
          </div>
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            <Info label="البريد الإلكتروني" value={user.email} />
            <Info label="الدور" value={roleLabels[user.role]} />
            <Info label="المؤسسة" value={user.institution ?? "—"} />
          </div>
        </Card>
      </div>
    </AppShell>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-muted p-4">
      <p className="text-xs font-bold text-muted-foreground">{label}</p>
      <p className="mt-2 font-bold text-foreground">{value}</p>
    </div>
  );
}
