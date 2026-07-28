import { AppShell } from "@/components/layout/app-shell";
import dynamic from "next/dynamic";
import { FormSkeleton } from "@/components/shared/route-skeleton";
import { SectionTitle } from "@/components/ui/card";
import { projectsService } from "@/services/projects-service";

const StoryEditor = dynamic(() => import("@/components/stories/story-editor").then((mod) => mod.StoryEditor), {
  loading: () => <FormSkeleton />,
});

export default async function StoryEditorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const editorData = await projectsService.getEditorData(id);
  return (
    <AppShell title="محرر القصة">
      <div className="space-y-6">
        <SectionTitle title="محرر القصة" subtitle="راجع النص والشخصيات والأهداف التعليمية قبل تحويل القصة إلى لوحات قصصية." />
        <StoryEditor data={editorData} />
      </div>
    </AppShell>
  );
}
