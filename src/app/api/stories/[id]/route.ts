import { getStoryForUser } from "@/lib/story-repository";
import { requireStoryUserId } from "@/lib/story-auth";
import { apiSuccess } from "@/server/responses/api-response";
import { handleApiError } from "@/server/errors/error-handler";
import { AppError } from "@/server/errors/app-error";

export const runtime = "nodejs";
export const maxDuration = 900;
export const dynamic = "force-dynamic";

function sanitizeUrl(url?: string): string | undefined {
  if (!url) return undefined;
  if (url.startsWith("file://") || url.includes("/temp/")) {
    const norm = url.replace("file://", "").replace(/\\/g, "/");
    const tempIndex = norm.indexOf("/temp/");
    if (tempIndex !== -1) {
      return `http://127.0.0.1:8000${norm.substring(tempIndex)}`;
    }
  }
  return url;
}

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  try {
    const userId = await requireStoryUserId();

    const story = await getStoryForUser(id, userId);
    if (!story) throw AppError.notFound("القصة غير موجودة أو لا تملك صلاحية الوصول إليها.");

    // Sanitize any file:// URLs to HTTP static URLs
    if (story.assets) {
      story.assets.presentationUrl = sanitizeUrl(story.assets.presentationUrl);
      story.assets.videoUrl = sanitizeUrl(story.assets.videoUrl);
      story.assets.thumbnailUrl = sanitizeUrl(story.assets.thumbnailUrl);
      story.assets.combinedAudioUrl = sanitizeUrl(story.assets.combinedAudioUrl);
      story.assets.combinedVideoUrl = sanitizeUrl(story.assets.combinedVideoUrl);
      story.assets.combinedNarratedVideoUrl = sanitizeUrl(story.assets.combinedNarratedVideoUrl);
    }
    if (story.scenes) {
      story.scenes = story.scenes.map((scene) => ({
        ...scene,
        imageUrl: sanitizeUrl(scene.imageUrl),
        audioUrl: sanitizeUrl(scene.audioUrl),
        videoUrl: sanitizeUrl(scene.videoUrl),
      }));
    }

    return apiSuccess({ story });
  } catch (error) {
    return handleApiError(error, { route: "GET /api/stories/[id]", storyId: id });
  }
}
