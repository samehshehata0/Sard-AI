import { AppShell } from "@/components/layout/app-shell";
import dynamic from "next/dynamic";
import { MediaSkeleton } from "@/components/shared/route-skeleton";
import { Card, SectionTitle } from "@/components/ui/card";
import { projectsService } from "@/services/projects-service";

const AudioPlayerCard = dynamic(() => import("@/components/media/audio-player-card").then((mod) => mod.AudioPlayerCard), {
  loading: () => <MediaSkeleton />,
});

export default async function AudioPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const scenes = await projectsService.getScenes(id);
  return (
    <AppShell title="التعليق الصوتي">
      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <div className="space-y-6">
          <SectionTitle title="معاينة التعليق الصوتي" subtitle="اضبط نوع الصوت والسرعة والنبرة، ثم راجع نصوص المشاهد." />
          <AudioPlayerCard />
        </div>
        <Card>
          <h3 className="font-heading text-xl font-extrabold text-foreground">نصوص المشاهد</h3>
          <div className="mt-5 space-y-3">
            {scenes.map((scene) => (
              <div key={scene.number} className="rounded-2xl bg-muted p-4">
                <p className="text-sm font-bold text-primary">{scene.title}</p>
                <p className="mt-2 text-sm leading-7 text-muted-foreground">{scene.narration}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
