import { endpoints } from "@/lib/api/endpoints";
import { apiRequest, isApiConfigured } from "@/services/api-client";
import { mockAssessment } from "@/services/mock-data";
import type { Assessment, CreateAssessmentInput } from "@/types/assessment";

export const assessmentsService = {
  create: (projectId: string, input: CreateAssessmentInput) => isApiConfigured ? apiRequest<Assessment>(endpoints.projects.assessments(projectId), { method: "POST", body: input }) : Promise.resolve({ ...mockAssessment, projectId, ...input }),
  latest: (projectId: string) => isApiConfigured ? apiRequest<Assessment>(endpoints.projects.latestAssessment(projectId)) : Promise.resolve({ ...mockAssessment, projectId }),
};
