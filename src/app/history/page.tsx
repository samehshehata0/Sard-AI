import { AppShell } from "@/components/layout/app-shell";
import { StoryHistory } from "@/components/stories/story-history";
import { SectionTitle } from "@/components/ui/card";

export default function HistoryPage() {
  return <AppShell title="السجل"><div className="space-y-6"><SectionTitle title="سجل القصص" subtitle="استعرض قصصك الفعلية المحفوظة في MongoDB وحالتها الحالية." /><StoryHistory /></div></AppShell>;
}
