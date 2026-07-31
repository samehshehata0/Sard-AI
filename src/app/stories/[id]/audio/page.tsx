import { AppShell } from "@/components/layout/app-shell";
import { StoryWorkspace } from "@/components/stories/story-workspace";

export default async function AudioPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AppShell title="التعليق الصوتي"><StoryWorkspace storyId={id} view="audio" /></AppShell>;
}
