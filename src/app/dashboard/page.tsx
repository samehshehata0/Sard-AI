import { ArrowLeft, BarChart3, BookOpen, Clock3 } from "lucide-react";
import { StatCard } from "@/components/dashboard/stat-card";
import { WellBeingIndexCard } from "@/components/dashboard/well-being-index-card";
import { AppShell } from "@/components/layout/app-shell";
import { StoryCard } from "@/components/shared/story-card";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card } from "@/components/ui/card";
import { requireUser } from "@/server/auth/session";
import { mockDashboardStats } from "@/services/mock-data";
import { projectsService } from "@/services/projects-service";

export default async function DashboardPage() {
  const [user, stories] = await Promise.all([requireUser(), projectsService.getCards()]);
  return (
    <AppShell title="لوحة التحكم">
      <div className="space-y-6">
        <Card className="bg-gradient-to-l from-primary to-secondary text-primary-foreground">
          <div className="flex flex-col justify-between gap-5 md:flex-row md:items-center">
            <div>
              <h2 className="font-heading text-3xl font-black">مرحبًا، {user.fullName} 👋</h2>
              <p className="mt-3 text-lg text-primary-foreground/85">لنبدأ إنشاء قصة تعليمية جديدة اليوم</p>
            </div>
            <ArabicButton href="/stories/new" variant="secondary" icon={<ArrowLeft className="h-4 w-4 rtl-icon" />}>إنشاء قصة جديدة</ArabicButton>
          </div>
        </Card>
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {mockDashboardStats.map((stat) => <StatCard key={stat.label} {...stat} />)}
        </div>
        <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
          <div>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-heading text-2xl font-extrabold text-foreground">القصص الأخيرة</h2>
              <ArabicButton href="/history" variant="ghost">عرض الكل</ArabicButton>
            </div>
            <div className="grid gap-5 md:grid-cols-2">
              {stories.slice(0, 2).map((story) => <StoryCard key={story.id} story={story} />)}
            </div>
          </div>
          <div className="space-y-6">
            <WellBeingIndexCard />
            <Card>
              <h3 className="font-heading text-xl font-extrabold text-foreground">إجراءات سريعة</h3>
              <div className="mt-5 grid gap-3">
                <ArabicButton href="/stories/new" variant="outline" icon={<BookOpen className="h-4 w-4" />}>إنشاء قصة</ArabicButton>
                <ArabicButton href="/stories/demo-story/reports" variant="outline" icon={<BarChart3 className="h-4 w-4" />}>عرض التقارير</ArabicButton>
                <ArabicButton href="/history" variant="outline" icon={<Clock3 className="h-4 w-4" />}>مراجعة القصص السابقة</ArabicButton>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
