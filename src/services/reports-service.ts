import { endpoints } from "@/lib/api/endpoints";
import { apiRequest, isApiConfigured } from "@/services/api-client";
import { mockReport } from "@/services/mock-data";
import type { ReportView } from "@/types/report";

export const reportsService = {
  getByProjectId: (projectId: string): Promise<ReportView> => isApiConfigured ? apiRequest<ReportView>(endpoints.projects.report(projectId)) : Promise.resolve({ ...mockReport, projectId }),
};
