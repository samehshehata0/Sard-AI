import "server-only";

import { AppError } from "@/server/errors/app-error";
import { connectToDatabase } from "@/server/database/connection";
import { ProjectModel } from "@/server/database/models/project.model";
import { GenerationJobModel } from "@/server/database/models/generation-job.model";

export function assertOwnership(ownerId: unknown, authenticatedUserId: string): void {
  if (String(ownerId) !== authenticatedUserId) throw AppError.notFound();
}

export function ownedByUserFilter(userId: string) {
  return { userId };
}

export async function requireOwnedProject(projectId: string, userId: string) {
  await connectToDatabase();
  const project = await ProjectModel.findOne({ _id: projectId, userId });
  if (!project) throw AppError.notFound("المشروع المطلوب غير موجود.");
  return project;
}

export async function requireOwnedGenerationJob(jobId: string, userId: string) {
  await connectToDatabase();
  const job = await GenerationJobModel.findOne({ _id: jobId, userId });
  if (!job) throw AppError.notFound("مهمة التوليد المطلوبة غير موجودة.");
  return job;
}
