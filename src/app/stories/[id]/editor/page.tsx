import { redirect } from "next/navigation";

export default async function StoryEditorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/stories/${id}/storyboard`);
}
