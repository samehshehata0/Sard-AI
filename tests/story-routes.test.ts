import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppError } from "@/server/errors/app-error";

vi.mock("@/lib/services/job-queue", () => ({
  enqueueStoryJob: vi.fn(),
  cancelStoryJob: vi.fn(),
  syncStoryWithJob: vi.fn(async (story: unknown) => story),
  isAwaitingJob: vi.fn(),
}));
vi.mock("@/server/auth/session", () => ({ requireUser: vi.fn() }));
vi.mock("@/lib/story-repository", () => ({
  listStoriesForUser: vi.fn(),
  getStoryForUser: vi.fn(),
  createStory: vi.fn(),
  createQueuedStory: vi.fn(),
  resetStoryForRetry: vi.fn(),
  updateStoryProgress: vi.fn(),
  saveGeneratedScript: vi.fn(),
  completeStory: vi.fn(),
  failStory: vi.fn(),
}));

import { requireUser } from "@/server/auth/session";
import {
  listStoriesForUser,
  getStoryForUser,
  createStory,
  createQueuedStory,
  resetStoryForRetry,
  failStory,
} from "@/lib/story-repository";
import { cancelStoryJob, enqueueStoryJob, isAwaitingJob, syncStoryWithJob } from "@/lib/services/job-queue";
import { GET as listStories, POST as createStoryRoute } from "@/app/api/stories/route";
import { GET as getStory } from "@/app/api/stories/[id]/route";
import { POST as retryStory } from "@/app/api/stories/[id]/retry/route";
import { POST as cancelStory } from "@/app/api/stories/[id]/cancel/route";
import { POST as rebuildVideo } from "@/app/api/stories/[id]/video/rebuild/route";

const mockedRequireUser = vi.mocked(requireUser);
const mockedListStoriesForUser = vi.mocked(listStoriesForUser);
const mockedGetStoryForUser = vi.mocked(getStoryForUser);
const mockedCreateStory = vi.mocked(createStory);
const mockedCreateQueuedStory = vi.mocked(createQueuedStory);
const mockedResetStoryForRetry = vi.mocked(resetStoryForRetry);
const mockedFailStory = vi.mocked(failStory);
const mockedEnqueue = vi.mocked(enqueueStoryJob);
const mockedCancelJob = vi.mocked(cancelStoryJob);
const accepted = { duplicate: false, storyId: "s1" };
const mockedSync = vi.mocked(syncStoryWithJob);
const mockedIsAwaitingJob = vi.mocked(isAwaitingJob);

const user = {
  id: "507f1f77bcf86cd799439011",
  fullName: "سامح أحمد",
  email: "sameh@example.com",
  role: "student_teacher" as const,
  institution: null,
  avatarUrl: null,
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
};

function getRequest(url: string, originHeader?: string) {
  return new Request(url, { headers: originHeader ? { origin: originHeader } : {} });
}

function postRequest(url: string, body?: unknown, originHeader?: string) {
  return new Request(url, {
    method: "POST",
    headers: { "content-type": "application/json", ...(originHeader ? { origin: originHeader } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

function params(id: string) {
  return { params: Promise.resolve({ id }) };
}

describe("story route handlers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedSync.mockImplementation(async (story) => story);
    mockedFailStory.mockResolvedValue(undefined);
    mockedCancelJob.mockResolvedValue(undefined);
    mockedCreateStory.mockResolvedValue(undefined);
    mockedEnqueue.mockResolvedValue(accepted);
  });

  describe("GET /api/stories", () => {
    it("rejects unauthenticated requests", async () => {
      mockedRequireUser.mockRejectedValue(AppError.authentication());
      const response = await listStories();
      expect(response.status).toBe(401);
      expect(mockedListStoriesForUser).not.toHaveBeenCalled();
    });

    it("returns the authenticated user's stories", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedListStoriesForUser.mockResolvedValue([{ _id: "s1" }] as never);
      const response = await listStories();
      const body = await response.json();
      expect(response.status).toBe(200);
      expect(body.data.stories).toEqual([{ _id: "s1" }]);
      expect(mockedListStoriesForUser).toHaveBeenCalledWith(user.id);
    });

    it("brings stories that are still waiting on a job up to date before listing them", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedIsAwaitingJob.mockImplementation((story) => story.status === "generating");
      mockedListStoriesForUser
        .mockResolvedValueOnce([{ _id: "s1", status: "generating", jobId: "j1" }, { _id: "s2", status: "completed" }] as never)
        .mockResolvedValueOnce([{ _id: "s1", status: "completed" }, { _id: "s2", status: "completed" }] as never);
      const response = await listStories();
      const body = await response.json();
      expect(mockedSync).toHaveBeenCalledTimes(1);
      expect(mockedSync).toHaveBeenCalledWith(expect.objectContaining({ _id: "s1" }), user.id);
      expect(body.data.stories[0].status).toBe("completed");
    });

    it("does not call the job backend when nothing is waiting", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedIsAwaitingJob.mockReturnValue(false);
      mockedListStoriesForUser.mockResolvedValue([{ _id: "s2", status: "completed" }] as never);
      await listStories();
      expect(mockedSync).not.toHaveBeenCalled();
      expect(mockedListStoriesForUser).toHaveBeenCalledTimes(1);
    });
  });

  describe("POST /api/stories", () => {
    it("rejects unauthenticated requests", async () => {
      mockedRequireUser.mockRejectedValue(AppError.authentication());
      const response = await createStoryRoute(postRequest("http://localhost/api/stories", { title: "قصة" }));
      expect(response.status).toBe(401);
      expect(mockedCreateQueuedStory).not.toHaveBeenCalled();
    });

    it("rejects cross-origin requests", async () => {
      const response = await createStoryRoute(postRequest("http://localhost/api/stories", { title: "قصة" }, "http://evil.example"));
      expect(response.status).toBe(403);
      expect(mockedRequireUser).not.toHaveBeenCalled();
    });

    it("creates a story scoped to the session user and queues a job, with no cookie minted", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedCreateQueuedStory.mockReturnValue({ _id: "s1", userId: user.id } as never);
      const response = await createStoryRoute(postRequest("http://localhost/api/stories", { title: "قصة تعليمية" }));
      const body = await response.json();
      expect(response.status).toBe(202);
      expect(typeof body.data.storyId).toBe("string");
      expect(response.headers.get("set-cookie")).toBeNull();
      expect(mockedCreateQueuedStory).toHaveBeenCalledWith(
        expect.any(String),
        user.id,
        expect.anything(),
        expect.any(Number),
        expect.any(Number),
        expect.any(String),
      );
      expect(mockedCreateStory).toHaveBeenCalledWith({ _id: "s1", userId: user.id });
    });

    it("asks the queue first, for this user, handing it the same story and job ids", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedCreateQueuedStory.mockReturnValue({ _id: "s1", userId: user.id } as never);
      const response = await createStoryRoute(postRequest("http://localhost/api/stories", { title: "قصة تعليمية" }));
      const body = await response.json();
      const [storyId, jobId, userId, input] = mockedEnqueue.mock.calls[0];
      expect(storyId).toBe(body.data.storyId);
      expect(userId).toBe(user.id);
      expect(mockedCreateQueuedStory.mock.calls[0][5]).toBe(jobId);
      expect(input.title).toBe("قصة تعليمية");
      expect(mockedEnqueue.mock.invocationCallOrder[0]).toBeLessThan(mockedCreateStory.mock.invocationCallOrder[0]);
    });

    it("answers with the existing story, and creates none, when the same request is already queued", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedEnqueue.mockResolvedValue({ duplicate: true, storyId: "existing-story" });
      const response = await createStoryRoute(postRequest("http://localhost/api/stories", { title: "قصة" }));
      const body = await response.json();
      expect(response.status).toBe(200);
      expect(body.data).toMatchObject({ storyId: "existing-story", duplicate: true });
      expect(mockedCreateStory).not.toHaveBeenCalled();
    });

    it("answers 429 with the queue's message when the user has too many active jobs, and creates no story", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedEnqueue.mockRejectedValue(AppError.rateLimited("وصلت إلى الحد الأقصى للطلبات قيد المعالجة (2)."));
      const response = await createStoryRoute(postRequest("http://localhost/api/stories", { title: "قصة" }));
      const body = await response.json();
      expect(response.status).toBe(429);
      expect(body.error.message).toBe("وصلت إلى الحد الأقصى للطلبات قيد المعالجة (2).");
      expect(mockedCreateStory).not.toHaveBeenCalled();
    });

    it("refuses with 503 and creates no story when the queue cannot take the job", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedEnqueue.mockRejectedValue(AppError.databaseUnavailable("قائمة الانتظار غير متاحة مؤقتًا."));
      const response = await createStoryRoute(postRequest("http://localhost/api/stories", { title: "قصة" }));
      const body = await response.json();
      expect(response.status).toBe(503);
      expect(body.error.message).toBe("قائمة الانتظار غير متاحة مؤقتًا.");
      expect(mockedCreateStory).not.toHaveBeenCalled();
      expect(mockedFailStory).not.toHaveBeenCalled();
    });

    it("takes the job back out of the queue when the story could not be saved", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedCreateQueuedStory.mockReturnValue({ _id: "s1" } as never);
      mockedCreateStory.mockRejectedValue(new Error("mongo down"));
      const response = await createStoryRoute(postRequest("http://localhost/api/stories", { title: "قصة" }));
      expect(response.status).toBe(503);
      const [, jobId, userId] = mockedEnqueue.mock.calls[0];
      expect(mockedCancelJob).toHaveBeenCalledWith(jobId, userId);
    });
  });

  describe("GET /api/stories/[id]", () => {
    it("rejects unauthenticated requests", async () => {
      mockedRequireUser.mockRejectedValue(AppError.authentication());
      const response = await getStory(getRequest("http://localhost/api/stories/s1"), params("s1"));
      expect(response.status).toBe(401);
      expect(mockedGetStoryForUser).not.toHaveBeenCalled();
    });

    it("returns 404 when the story isn't owned by the session user", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedGetStoryForUser.mockResolvedValue(null);
      const response = await getStory(getRequest("http://localhost/api/stories/s1"), params("s1"));
      expect(response.status).toBe(404);
    });

    it("returns the story scoped to the session user", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedGetStoryForUser.mockResolvedValue({ _id: "s1", scenes: [], assets: {} } as never);
      const response = await getStory(getRequest("http://localhost/api/stories/s1"), params("s1"));
      const body = await response.json();
      expect(response.status).toBe(200);
      expect(body.data.story._id).toBe("s1");
      expect(mockedGetStoryForUser).toHaveBeenCalledWith("s1", user.id);
    });

    it("returns the story as updated from its job", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedGetStoryForUser.mockResolvedValue({ _id: "s1", status: "generating", jobId: "j1", scenes: [], assets: {} } as never);
      mockedSync.mockResolvedValue({ _id: "s1", status: "completed", jobId: "j1", scenes: [], assets: {} } as never);
      const response = await getStory(getRequest("http://localhost/api/stories/s1"), params("s1"));
      const body = await response.json();
      expect(mockedSync).toHaveBeenCalledWith(expect.objectContaining({ _id: "s1" }), user.id);
      expect(body.data.story.status).toBe("completed");
    });
  });

  describe("POST /api/stories/[id]/retry", () => {
    it("rejects unauthenticated requests", async () => {
      mockedRequireUser.mockRejectedValue(AppError.authentication());
      const response = await retryStory(postRequest("http://localhost/api/stories/s1/retry"), params("s1"));
      expect(response.status).toBe(401);
    });

    it("rejects cross-origin requests", async () => {
      const response = await retryStory(postRequest("http://localhost/api/stories/s1/retry", undefined, "http://evil.example"), params("s1"));
      expect(response.status).toBe(403);
    });

    it("returns 404 when the story isn't owned by the session user", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedGetStoryForUser.mockResolvedValue(null);
      const response = await retryStory(postRequest("http://localhost/api/stories/s1/retry"), params("s1"));
      expect(response.status).toBe(404);
    });

    it("rejects retrying a story that isn't failed", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedGetStoryForUser.mockResolvedValue({ _id: "s1", status: "completed", input: {} } as never);
      const response = await retryStory(postRequest("http://localhost/api/stories/s1/retry"), params("s1"));
      expect(response.status).toBe(409);
    });

    it("retries a failed story owned by the session user", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedGetStoryForUser.mockResolvedValue({ _id: "s1", status: "failed", input: {} } as never);
      mockedResetStoryForRetry.mockResolvedValue(true);
      mockedEnqueue.mockResolvedValue(accepted);
      const response = await retryStory(postRequest("http://localhost/api/stories/s1/retry"), params("s1"));
      const body = await response.json();
      expect(response.status).toBe(202);
      expect(body.data.status).toBe("queued");
      expect(mockedGetStoryForUser).toHaveBeenCalledWith("s1", user.id);
    });

    it("queues a fresh job for the retry and points the story at it", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedGetStoryForUser.mockResolvedValue({ _id: "s1", status: "failed", input: { title: "قصة" } } as never);
      mockedResetStoryForRetry.mockResolvedValue(true);
      mockedEnqueue.mockResolvedValue(accepted);
      await retryStory(postRequest("http://localhost/api/stories/s1/retry"), params("s1"));
      const [, , jobId] = mockedResetStoryForRetry.mock.calls[0];
      expect(mockedResetStoryForRetry).toHaveBeenCalledWith("s1", user.id, expect.any(String));
      expect(mockedEnqueue).toHaveBeenCalledWith("s1", jobId, user.id, { title: "قصة" });
    });

    it("answers 429 and stops the story again when the user is over their limit", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedGetStoryForUser.mockResolvedValue({ _id: "s1", status: "failed", input: {} } as never);
      mockedResetStoryForRetry.mockResolvedValue(true);
      mockedEnqueue.mockRejectedValue(AppError.rateLimited("وصلت إلى الحد الأقصى للطلبات قيد المعالجة (2)."));
      const response = await retryStory(postRequest("http://localhost/api/stories/s1/retry"), params("s1"));
      expect(response.status).toBe(429);
      expect(mockedFailStory).toHaveBeenCalledWith("s1", "وصلت إلى الحد الأقصى للطلبات قيد المعالجة (2).");
    });

    it("answers 409 when an identical request is already queued", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedGetStoryForUser.mockResolvedValue({ _id: "s1", status: "failed", input: {} } as never);
      mockedResetStoryForRetry.mockResolvedValue(true);
      mockedEnqueue.mockResolvedValue({ duplicate: true, storyId: "other" });
      const response = await retryStory(postRequest("http://localhost/api/stories/s1/retry"), params("s1"));
      expect(response.status).toBe(409);
      expect(mockedFailStory).toHaveBeenCalledWith("s1", "يوجد طلب مطابق قيد المعالجة بالفعل.");
    });

    it("fails the story again and answers 503 when the retry cannot be queued", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedGetStoryForUser.mockResolvedValue({ _id: "s1", status: "failed", input: {} } as never);
      mockedResetStoryForRetry.mockResolvedValue(true);
      mockedEnqueue.mockRejectedValue(AppError.databaseUnavailable("قائمة الانتظار غير متاحة مؤقتًا."));
      const response = await retryStory(postRequest("http://localhost/api/stories/s1/retry"), params("s1"));
      expect(response.status).toBe(503);
      expect(mockedFailStory).toHaveBeenCalledWith("s1", "قائمة الانتظار غير متاحة مؤقتًا.");
    });
  });

  describe("POST /api/stories/[id]/cancel", () => {
    it("rejects unauthenticated requests", async () => {
      mockedRequireUser.mockRejectedValue(AppError.authentication());
      const response = await cancelStory(postRequest("http://localhost/api/stories/s1/cancel"), params("s1"));
      expect(response.status).toBe(401);
    });

    it("rejects cross-origin requests", async () => {
      const response = await cancelStory(postRequest("http://localhost/api/stories/s1/cancel", undefined, "http://evil.example"), params("s1"));
      expect(response.status).toBe(403);
    });

    it("returns 404 when the story isn't owned by the session user", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedGetStoryForUser.mockResolvedValue(null);
      const response = await cancelStory(postRequest("http://localhost/api/stories/s1/cancel"), params("s1"));
      expect(response.status).toBe(404);
      expect(mockedCancelJob).not.toHaveBeenCalled();
    });

    it("cancels a queued story's job for the session user and stops the story", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedGetStoryForUser.mockResolvedValue({ _id: "s1", status: "queued", jobId: "j1" } as never);
      const response = await cancelStory(postRequest("http://localhost/api/stories/s1/cancel"), params("s1"));
      const body = await response.json();
      expect(response.status).toBe(200);
      expect(body.data.status).toBe("cancelled");
      expect(mockedCancelJob).toHaveBeenCalledWith("j1", user.id);
      expect(mockedFailStory).toHaveBeenCalledWith("s1", "أُلغي طلب التوليد.");
    });

    it("leaves the story alone when the queue says the job is already running", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedGetStoryForUser.mockResolvedValue({ _id: "s1", status: "generating", jobId: "j1" } as never);
      mockedCancelJob.mockRejectedValue(AppError.conflict("لا يمكن إلغاء مهمة قيد التنفيذ."));
      const response = await cancelStory(postRequest("http://localhost/api/stories/s1/cancel"), params("s1"));
      const body = await response.json();
      expect(response.status).toBe(409);
      expect(body.error.message).toBe("لا يمكن إلغاء مهمة قيد التنفيذ.");
      expect(mockedFailStory).not.toHaveBeenCalled();
    });

    it("refuses a story that already finished, without asking the queue", async () => {
      mockedRequireUser.mockResolvedValue(user);
      for (const status of ["completed", "failed"]) {
        mockedGetStoryForUser.mockResolvedValue({ _id: "s1", status, jobId: "j1" } as never);
        const response = await cancelStory(postRequest("http://localhost/api/stories/s1/cancel"), params("s1"));
        expect(response.status).toBe(409);
      }
      expect(mockedCancelJob).not.toHaveBeenCalled();
    });
  });

  describe("POST /api/stories/[id]/video/rebuild", () => {
    it("rejects unauthenticated requests", async () => {
      mockedRequireUser.mockRejectedValue(AppError.authentication());
      const response = await rebuildVideo(postRequest("http://localhost/api/stories/s1/video/rebuild"));
      expect(response.status).toBe(401);
    });

    it("rejects cross-origin requests", async () => {
      const response = await rebuildVideo(postRequest("http://localhost/api/stories/s1/video/rebuild", undefined, "http://evil.example"));
      expect(response.status).toBe(403);
    });

    it("acknowledges the request for an authenticated user", async () => {
      mockedRequireUser.mockResolvedValue(user);
      const response = await rebuildVideo(postRequest("http://localhost/api/stories/s1/video/rebuild"));
      const body = await response.json();
      expect(response.status).toBe(200);
      expect(body.data.status).toBe("completed");
    });
  });
});
