import Link from "next/link";
import { CalendarDays, Gauge } from "lucide-react";
import { Card } from "@/components/ui/card";
import { StoryStatus } from "@/lib/constants/types";

const statusClasses: Record<StoryStatus, string> = {
  مكتملة: "bg-success/10 text-success",
  مسودة: "bg-warning/10 text-warning",
  "قيد المعالجة": "bg-primary/10 text-primary",
};

export function StoryCard({ story }: { story: { id: string; title: string; topic: string; status: StoryStatus; date: string; quality: number; description: string } }) {
  return (
    <Card className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-heading text-xl font-extrabold text-foreground">{story.title}</h3>
          <p className="mt-1 text-sm font-bold text-primary">{story.topic}</p>
        </div>
        <span className={`shrink-0 rounded-full px-3 py-1 text-xs font-bold ${statusClasses[story.status]}`}>{story.status}</span>
      </div>
      <p className="mt-4 flex-1 text-sm leading-7 text-muted-foreground">{story.description}</p>
      <div className="mt-5 flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
        <span className="inline-flex items-center gap-2">
          <CalendarDays className="h-4 w-4" />
          {story.date}
        </span>
        <span className="inline-flex items-center gap-2">
          <Gauge className="h-4 w-4" />
          درجة الجودة {story.quality}%
        </span>
      </div>
      <Link href={`/stories/${story.id}/editor`} className="mt-5 inline-flex font-bold text-primary hover:opacity-80">
        فتح القصة
      </Link>
    </Card>
  );
}
