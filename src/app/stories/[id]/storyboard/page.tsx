import { AppShell } from "@/components/layout/app-shell";
import { StoryWorkspace } from "@/components/stories/story-workspace";

export default async function StoryboardPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AppShell title="اللوحات القصصية"><StoryWorkspace storyId={id} view="storyboard" /></AppShell>;
}
