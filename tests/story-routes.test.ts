import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppError } from "@/server/errors/app-error";

vi.mock("next/server", () => ({ after: vi.fn() }));
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
} from "@/lib/story-repository";
import { GET as listStories, POST as createStoryRoute } from "@/app/api/stories/route";
import { GET as getStory } from "@/app/api/stories/[id]/route";
import { POST as retryStory } from "@/app/api/stories/[id]/retry/route";
import { POST as rebuildVideo } from "@/app/api/stories/[id]/video/rebuild/route";

const mockedRequireUser = vi.mocked(requireUser);
const mockedListStoriesForUser = vi.mocked(listStoriesForUser);
const mockedGetStoryForUser = vi.mocked(getStoryForUser);
const mockedCreateStory = vi.mocked(createStory);
const mockedCreateQueuedStory = vi.mocked(createQueuedStory);
const mockedResetStoryForRetry = vi.mocked(resetStoryForRetry);

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
  beforeEach(() => vi.clearAllMocks());

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

    it("creates a story scoped to the session user, with no cookie minted", async () => {
      mockedRequireUser.mockResolvedValue(user);
      mockedCreateQueuedStory.mockReturnValue({ _id: "s1", userId: user.id } as never);
      const response = await createStoryRoute(postRequest("http://localhost/api/stories", { title: "قصة تعليمية" }));
      const body = await response.json();
      expect(response.status).toBe(202);
      expect(typeof body.data.storyId).toBe("string");
      expect(response.headers.get("set-cookie")).toBeNull();
      expect(mockedCreateQueuedStory).toHaveBeenCalledWith(expect.any(String), user.id, expect.anything(), expect.any(Number), expect.any(Number));
      expect(mockedCreateStory).toHaveBeenCalledWith({ _id: "s1", userId: user.id });
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
      const response = await retryStory(postRequest("http://localhost/api/stories/s1/retry"), params("s1"));
      const body = await response.json();
      expect(response.status).toBe(202);
      expect(body.data.status).toBe("queued");
      expect(mockedGetStoryForUser).toHaveBeenCalledWith("s1", user.id);
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
