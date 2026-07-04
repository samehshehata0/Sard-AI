import { AppShell } from "@/components/layout/app-shell";
import dynamic from "next/dynamic";
import { MediaSkeleton } from "@/components/shared/route-skeleton";
import { Card, SectionTitle } from "@/components/ui/card";
import { scenes } from "@/lib/constants/scenes-data";

const VideoPlayerCard = dynamic(() => import("@/components/media/video-player-card").then((mod) => mod.VideoPlayerCard), {
  loading: () => <MediaSkeleton />,
});

export default function VideoPage() {
  return (
    <AppShell title="الفيديو">
      <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <SectionTitle title="معاينة الفيديو" subtitle="راجع حالة الفيديو وتسلسل المشاهد قبل التحميل أو إعادة التوليد." />
          <VideoPlayerCard />
        </div>
        <Card>
          <h3 className="font-heading text-xl font-extrabold text-foreground">خط الزمن</h3>
          <div className="mt-5 space-y-3">
            {scenes.map((scene) => (
              <div key={scene.number} className="rounded-2xl bg-muted p-4">
                <p className="text-sm font-bold text-primary">المشهد {scene.number}</p>
                <p className="mt-1 font-bold text-foreground">{scene.title}</p>
              </div>
            ))}
          </div>
          <div className="mt-5 rounded-2xl bg-primary/10 p-4 text-sm font-bold text-primary">حالة الفيديو: قيد التحضير</div>
        </Card>
      </div>
    </AppShell>
  );
}
