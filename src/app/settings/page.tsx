import { AppShell } from "@/components/layout/app-shell";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { Card, SectionTitle } from "@/components/ui/card";

export default function SettingsPage() {
  return (
    <AppShell title="الإعدادات">
      <div className="space-y-6">
        <SectionTitle title="الإعدادات" subtitle="اضبط اللغة والمظهر والتنبيهات وتفضيلات الذكاء الاصطناعي والصوت." />
        <div className="grid gap-6 lg:grid-cols-2">
          <SettingsCard title="اللغة" items={["العربية"]} />
          <Card>
            <h3 className="font-heading text-xl font-extrabold text-foreground">المظهر</h3>
            <div className="mt-5">
              <ThemeToggle />
            </div>
          </Card>
          <SettingsCard title="تفضيلات الإشعارات" items={["تنبيه عند اكتمال القصة", "تنبيه عند جاهزية التقرير", "ملخص أسبوعي"]} />
          <SettingsCard title="تفضيلات الذكاء الاصطناعي" items={["لغة عربية مبسطة", "مراجعة تربوية تلقائية", "اقتراح أسئلة ختامية"]} />
          <SettingsCard title="تفضيلات الصوت" items={["صوت عربي هادئ", "سرعة متوسطة", "نبرة مشجعة"]} />
        </div>
      </div>
    </AppShell>
  );
}

function SettingsCard({ title, items }: { title: string; items: string[] }) {
  return (
    <Card>
      <h3 className="font-heading text-xl font-extrabold text-foreground">{title}</h3>
      <div className="mt-5 space-y-3">
        {items.map((item) => (
          <label key={item} className="flex items-center justify-between rounded-2xl bg-muted p-4 text-sm font-bold text-foreground">
            <span>{item}</span>
            <input type="checkbox" defaultChecked className="h-5 w-5 rounded border-border accent-primary" />
          </label>
        ))}
      </div>
    </Card>
  );
}
