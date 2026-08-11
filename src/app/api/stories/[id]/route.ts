import { getStoryForUser } from "@/lib/story-repository";

export const runtime = "nodejs";
export const maxDuration = 900;
export const dynamic = "force-dynamic";

const USER_COOKIE = "sard_user_id";

function getUserId(request: Request) {
  const cookieHeader = request.headers.get("cookie") || "";
  return cookieHeader.match(new RegExp(`(?:^|;\\s*)${USER_COOKIE}=([^;]+)`))?.[1];
}

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
  const userId = getUserId(request);
  if (!userId) return Response.json({ error: "تعذر تحديد مستخدم القصة. أنشئ القصة من هذا المتصفح أولاً." }, { status: 401 });

  const { id } = await context.params;
  try {
    const story = await getStoryForUser(id, userId);
    if (!story) return Response.json({ error: "القصة غير موجودة أو لا تملك صلاحية الوصول إليها." }, { status: 404 });

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

    return Response.json({ story });
  } catch (error) {
    console.error(`[Sard][${id}] تعذر قراءة القصة من MongoDB:`, error);
    return Response.json({ error: "تعذر قراءة القصة من MongoDB. راجع طرفية الخادم للتفاصيل." }, { status: 500 });
  }
}
