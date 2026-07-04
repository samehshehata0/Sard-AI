import { AppShell } from "@/components/layout/app-shell";
import { SceneCard } from "@/components/storyboard/scene-card";
import { SectionTitle } from "@/components/ui/card";
import { scenes } from "@/lib/constants/scenes-data";

export default function StoryboardPage() {
  return (
    <AppShell title="اللوحات القصصية">
      <div className="space-y-6">
        <SectionTitle title="اللوحات القصصية" subtitle="كل مشهد يحتوي وصفًا بصريًا، نصًا صوتيًا، ومطالبة جاهزة للصورة أو الفيديو." />
        <div className="space-y-5">
          {scenes.map((scene) => <SceneCard key={scene.number} scene={scene} />)}
        </div>
      </div>
    </AppShell>
  );
}
