import { Search } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { StoryCard } from "@/components/shared/story-card";
import { SectionTitle } from "@/components/ui/card";
import { projectsService } from "@/services/projects-service";

export default async function HistoryPage() {
  const stories = await projectsService.getCards();
  return (
    <AppShell title="السجل">
      <div className="space-y-6">
        <SectionTitle title="سجل القصص" subtitle="استعرض القصص السابقة وفلترها حسب الحالة أو ابحث باسم القصة والموضوع." />
        <div className="flex flex-col gap-3 rounded-3xl border border-border bg-card p-4 shadow-sm md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap gap-2">
            {["الكل", "مكتملة", "مسودة", "قيد المعالجة"].map((filter) => (
              <button key={filter} className="rounded-full bg-muted px-4 py-2 text-sm font-bold text-muted-foreground hover:bg-primary/10 hover:text-primary">{filter}</button>
            ))}
          </div>
          <div className="flex items-center gap-2 rounded-2xl border border-border px-4 py-3 md:w-80">
            <Search className="h-5 w-5 text-muted-foreground" />
            <input className="w-full bg-transparent text-sm outline-none" placeholder="ابحث في السجل" />
          </div>
        </div>
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {stories.map((story) => <StoryCard key={story.id} story={story} />)}
        </div>
      </div>
    </AppShell>
  );
}
