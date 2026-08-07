import { describe, expect, it } from "vitest";
import { Types } from "mongoose";
import { AssessmentModel } from "@/server/database/models/assessment.model";
import { ProjectModel } from "@/server/database/models/project.model";
import { UserModel } from "@/server/database/models/user.model";

describe("Mongoose model validation", () => {
  it("normalizes email and omits passwordHash from JSON", async () => {
    const user = new UserModel({
      fullName: "سامح أحمد",
      email: "  SAMEH@EXAMPLE.COM ",
      passwordHash: "hashed-value",
      role: "student_teacher",
    });
    await user.validate();
    expect(user.email).toBe("sameh@example.com");
    expect(user.toJSON()).not.toHaveProperty("passwordHash");
  });

  it("rejects duplicate requested outputs", async () => {
    const project = new ProjectModel({
      userId: new Types.ObjectId(),
      title: "قصة",
      educationalTopic: "الماء",
      learningObjectives: ["هدف"],
      learnerAge: "9",
      educationLevel: "ابتدائي",
      learnerCharacteristics: "تعلم بصري",
      storyStyle: "حواري",
      voiceTone: "هادئة",
      requestedOutputs: ["audio", "audio"],
      prompt: "مطالبة",
    });
    await expect(project.validate()).rejects.toThrow();
  });

  it("rejects assessment answers and scores outside allowed ranges", async () => {
    const assessment = new AssessmentModel({
      projectId: new Types.ObjectId(),
      userId: new Types.ObjectId(),
      stressAnswers: [6],
      motivationAnswers: [4],
      stressScore: 110,
      motivationScore: 80,
      wellBeingScore: 80,
    });
    await expect(assessment.validate()).rejects.toThrow();
  });
});
