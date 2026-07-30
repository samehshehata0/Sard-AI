import { redirect } from "next/navigation";

export default async function StoryReportsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/stories/${id}/storyboard`);
}
