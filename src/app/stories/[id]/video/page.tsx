import { AppShell } from "@/components/layout/app-shell";
import { StoryWorkspace } from "@/components/stories/story-workspace";

export default async function VideoPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AppShell title="الفيديو"><StoryWorkspace storyId={id} view="video" /></AppShell>;
}
