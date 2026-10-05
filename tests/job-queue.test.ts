import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppError } from "@/server/errors/app-error";

vi.mock("@/lib/story-repository", () => ({
  completeStory: vi.fn(),
  failStory: vi.fn(),
  getStoryForUser: vi.fn(),
  saveGeneratedScript: vi.fn(),
  updateStoryProgress: vi.fn(),
}));

import {
  completeStory,
  failStory,
  getStoryForUser,
  saveGeneratedScript,
  updateStoryProgress,
} from "@/lib/story-repository";
import {
  buildJobPayload,
  enqueueStoryJob,
  fetchJob,
  isAwaitingJob,
  mapJobResultToStory,
  syncStoryWithJob,
} from "@/lib/services/job-queue";
import type { StoryDocument, StoryInput } from "@/lib/story-types";

const input: StoryInput & { custom_instructions?: string } = {
  title: "قصة الشمس",
  topic: "كيف تشرق الشمس",
  stage: "المرحلة الابتدائية",
  duration: "تلقائي",
  objectives: ["فهم دورة النهار"],
  age: "8 سنوات",
  level: "مبتدئ",
  needs: "لا يوجد",
  style: "رسوم",
  tone: "ودود",
  output: "نص + صوت + فيديو",
  speakerGender: "female",
  custom_instructions: "بدون موسيقى",
};

function story(overrides: Partial<StoryDocument> = {}): StoryDocument {
  return {
    _id: "s1",
    userId: "u1",
    jobId: "j1",
    input,
    status: "queued",
    progress: 0,
    currentStep: "",
    totalDurationSeconds: 60,
    sceneCount: 1,
    scenes: [],
    assets: {},
    logs: [],
    createdAt: new Date(),
    updatedAt: new Date(),
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const fetchMock = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("fetch", fetchMock);
  vi.mocked(getStoryForUser).mockResolvedValue(story({ status: "completed" }));
});

afterEach(() => vi.unstubAllGlobals());

describe("enqueueStoryJob", () => {
  it("posts the story to the job queue under the given ids", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ job_id: "j1", state: "queued" }, 202));
    await enqueueStoryJob("s1", "j1", input);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8000/jobs");
    expect(init.method).toBe("POST");
    const sent = JSON.parse(init.body);
    expect(sent).toMatchObject({
      job_id: "j1",
      story_id: "s1",
      story_title: "قصة الشمس",
      story_idea: "كيف تشرق الشمس",
      education_level: "المرحلة الابتدائية",
      narrator_gender: "female",
      output_type: "نص + صوت + فيديو",
      custom_instructions: "بدون موسيقى",
    });
  });

  it("maps every story field the backend expects", () => {
    expect(Object.keys(buildJobPayload("s1", "j1", input)).sort()).toEqual(
      [
        "custom_instructions", "education_level", "job_id", "learning_needs", "learning_objectives",
        "narrator_gender", "output_type", "story_duration", "story_id", "story_idea", "story_style",
        "story_title", "student_age", "student_level", "voice_tone",
      ].sort(),
    );
  });

  it("refuses with 503 when the queue's database is down", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "down" }, 503));
    await expect(enqueueStoryJob("s1", "j1", input)).rejects.toMatchObject({ statusCode: 503, code: "DATABASE_UNAVAILABLE" });
  });

  it("reports an unreachable backend as a provider failure in Arabic", async () => {
    fetchMock.mockRejectedValue(new Error("ECONNREFUSED"));
    const error = await enqueueStoryJob("s1", "j1", input).catch((e) => e);
    expect(error).toBeInstanceOf(AppError);
    expect(error.statusCode).toBe(502);
    expect(error.message).toContain("خدمة التوليد");
  });

  it("does not treat other errors as success", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "bad" }, 422));
    await expect(enqueueStoryJob("s1", "j1", input)).rejects.toMatchObject({ statusCode: 502 });
  });
});

describe("fetchJob", () => {
  it("returns the job", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ job_id: "j1", state: "running" }));
    expect(await fetchJob("j1")).toMatchObject({ state: "running" });
    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8000/jobs/j1");
  });

  it("returns null for a job the backend does not know", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "no" }, 404));
    expect(await fetchJob("j1")).toBeNull();
  });
});

describe("mapJobResultToStory", () => {
  it("maps scenes and assets from the pipeline result", () => {
    const { scenes, assets } = mapJobResultToStory(input, {
      video_url: "v.mp4",
      presentation_url: "d.pdf",
      thumbnail_url: "t.png",
      narration_audio_url: "n.mp3",
      scenes: [
        { scene_number: 1, title: "أ", duration_seconds: 5, narration_text: "نص", image_url: "1.png" },
        { scene_number: 2 },
      ],
    });
    expect(scenes).toHaveLength(2);
    expect(scenes[0]).toMatchObject({ number: 1, title: "أ", durationSeconds: 5, narration: "نص", imageUrl: "1.png", videoUrl: "v.mp4", audioUrl: "n.mp3" });
    expect(scenes[1]).toMatchObject({ number: 2, title: "المشهد 2", durationSeconds: 8, narration: "كيف تشرق الشمس", imageUrl: "t.png" });
    expect(assets).toMatchObject({ presentationUrl: "d.pdf", videoUrl: "v.mp4", thumbnailUrl: "t.png", combinedAudioUrl: "n.mp3" });
  });

  it("falls back to one scene when the result has none", () => {
    const { scenes } = mapJobResultToStory(input, { duration_seconds: 30, video_url: "v.mp4" });
    expect(scenes).toHaveLength(1);
    expect(scenes[0]).toMatchObject({ number: 1, title: "قصة الشمس", durationSeconds: 30, videoUrl: "v.mp4" });
  });
});

describe("syncStoryWithJob", () => {
  it("only looks at stories that are waiting on a job", async () => {
    for (const awaiting of [story({ status: "completed" }), story({ status: "failed" }), story({ jobId: undefined })]) {
      expect(isAwaitingJob(awaiting)).toBe(false);
      expect(await syncStoryWithJob(awaiting, "u1")).toBe(awaiting);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("leaves a queued story alone", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ job_id: "j1", state: "queued" }));
    const queued = story();
    expect(await syncStoryWithJob(queued, "u1")).toBe(queued);
    expect(updateStoryProgress).not.toHaveBeenCalled();
    expect(completeStory).not.toHaveBeenCalled();
  });

  it("shows a running job as generating with its step", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ job_id: "j1", state: "running", progress: 25, step: "جارٍ أتمتة NotebookLM" }));
    await syncStoryWithJob(story(), "u1");
    expect(updateStoryProgress).toHaveBeenCalledWith("s1", 25, "جارٍ أتمتة NotebookLM");
  });

  it("does not rewrite a story that already shows the running state", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ job_id: "j1", state: "running", progress: 25 }));
    await syncStoryWithJob(story({ status: "generating", progress: 25 }), "u1");
    expect(updateStoryProgress).not.toHaveBeenCalled();
  });

  it("completes the story from a finished job's result", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ job_id: "j1", state: "completed", result: { video_url: "v.mp4", presentation_url: "d.pdf", scenes: [{ scene_number: 1 }] } }),
    );
    const refreshed = story({ status: "completed", progress: 100 });
    vi.mocked(getStoryForUser).mockResolvedValue(refreshed);

    const result = await syncStoryWithJob(story({ status: "generating" }), "u1");

    expect(saveGeneratedScript).toHaveBeenCalledWith("s1", expect.objectContaining({ scenes: [expect.objectContaining({ number: 1 })] }));
    expect(completeStory).toHaveBeenCalledWith("s1", expect.objectContaining({ videoUrl: "v.mp4", presentationUrl: "d.pdf" }));
    expect(getStoryForUser).toHaveBeenCalledWith("s1", "u1");
    expect(result).toBe(refreshed);
  });

  it("fails the story with the job's Arabic error", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ job_id: "j1", state: "failed", error: "تعذر إنشاء العرض التعليمي" }));
    await syncStoryWithJob(story({ status: "generating" }), "u1");
    expect(failStory).toHaveBeenCalledWith("s1", "تعذر إنشاء العرض التعليمي");
    expect(completeStory).not.toHaveBeenCalled();
  });

  it("fails the story when the backend has no record of its job", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "no" }, 404));
    await syncStoryWithJob(story(), "u1");
    expect(failStory).toHaveBeenCalledWith("s1", expect.stringContaining("طلب التوليد"));
  });

  it("returns the story unchanged when the backend cannot be reached, so the next read retries", async () => {
    fetchMock.mockRejectedValue(new Error("ECONNREFUSED"));
    const waiting = story({ status: "generating" });
    expect(await syncStoryWithJob(waiting, "u1")).toBe(waiting);
    expect(failStory).not.toHaveBeenCalled();
  });
});
