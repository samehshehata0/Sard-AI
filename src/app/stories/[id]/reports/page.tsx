import { Download } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { ReportScoreCard } from "@/components/reports/report-score-card";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card, SectionTitle } from "@/components/ui/card";
import { report } from "@/lib/constants/report-data";

export default function ReportsPage() {
  return (
    <AppShell title="التقارير">
      <div className="space-y-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <SectionTitle title="تقرير جودة القصة" subtitle="ملخص تربوي يساعدك على تحسين القصة قبل مشاركتها مع المتعلمين." />
          <ArabicButton icon={<Download className="h-4 w-4" />}>تصدير PDF</ArabicButton>
        </div>
        <Card className="bg-gradient-to-l from-primary to-secondary text-primary-foreground">
          <p className="text-sm font-bold text-primary-foreground/80">التقييم العام</p>
          <p className="mt-2 font-numbers text-6xl font-bold">{report.overall}%</p>
          <p className="mt-3 text-primary-foreground/85">القصة جاهزة للمراجعة النهائية مع تحسينات بسيطة مقترحة.</p>
        </Card>
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-5">
          {report.scores.map((score) => <ReportScoreCard key={score.label} {...score} />)}
        </div>
        <div className="grid gap-6 lg:grid-cols-3">
          <List title="نقاط القوة" items={report.strengths} tone="green" />
          <List title="مجالات التحسين" items={report.improvements} tone="amber" />
          <List title="التوصيات" items={report.recommendations} tone="blue" />
        </div>
      </div>
    </AppShell>
  );
}

function List({ title, items, tone }: { title: string; items: readonly string[]; tone: "green" | "amber" | "blue" }) {
  const toneClass = tone === "green" ? "bg-success/10 text-success" : tone === "amber" ? "bg-warning/10 text-warning" : "bg-primary/10 text-primary";
  return (
    <Card>
      <h3 className="font-heading text-xl font-extrabold text-foreground">{title}</h3>
      <ul className="mt-5 space-y-3">
        {items.map((item) => <li key={item} className={`rounded-2xl p-4 text-sm font-bold leading-7 ${toneClass}`}>{item}</li>)}
      </ul>
    </Card>
  );
}
