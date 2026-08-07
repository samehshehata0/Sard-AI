import { ArrowLeft, BookOpen, Clock3 } from "lucide-react";
import { StoryGenerationStats } from "@/components/dashboard/story-generation-stats";
import { AppShell } from "@/components/layout/app-shell";
import { StoryHistory } from "@/components/stories/story-history";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card } from "@/components/ui/card";

export default async function DashboardPage() {
  const [user, stories] = await Promise.all([requireUser(), projectsService.getCards()]);
  return (
    <AppShell title="لوحة التحكم">
      <div className="space-y-6">
        <Card className="bg-gradient-to-l from-primary to-secondary text-primary-foreground">
          <div className="flex flex-col justify-between gap-5 md:flex-row md:items-center"><div><h2 className="font-heading text-3xl font-black">مرحباً بك 👋</h2><p className="mt-3 text-lg text-primary-foreground/85">ابدأ قصة تعليمية عربية جديدة أو تابع تقدم قصصك الفعلية.</p></div><ArabicButton href="/stories/new" variant="secondary" icon={<ArrowLeft className="h-4 w-4 rtl-icon" />}>إنشاء قصة جديدة</ArabicButton></div>
        </Card>
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4"><StoryGenerationStats /></div>
        <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
          <div><div className="mb-4 flex items-center justify-between"><h2 className="font-heading text-2xl font-extrabold text-foreground">أحدث القصص</h2><ArabicButton href="/history" variant="ghost">عرض الكل</ArabicButton></div><StoryHistory limit={2} /></div>
          <Card className="h-fit"><h3 className="font-heading text-xl font-extrabold text-foreground">إجراءات سريعة</h3><div className="mt-5 grid gap-3"><ArabicButton href="/stories/new" variant="outline" icon={<BookOpen className="h-4 w-4" />}>إنشاء قصة</ArabicButton><ArabicButton href="/history" variant="outline" icon={<Clock3 className="h-4 w-4" />}>مراجعة قصصك</ArabicButton></div></Card>
        </div>
      </div>
    </AppShell>
  );
}
