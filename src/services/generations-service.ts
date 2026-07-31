import { endpoints } from "@/lib/api/endpoints";
import { apiRequest, isApiConfigured } from "@/services/api-client";
import { mockGeneration } from "@/services/mock-data";
import type { GenerateAudioRequest, GenerateVideoRequest, GenerationJob } from "@/types/generation";

export const generationsService = {
  generateVideo: (projectId: string, input: GenerateVideoRequest = {}) => isApiConfigured ? apiRequest<GenerationJob>(endpoints.projects.generateVideo(projectId), { method: "POST", body: input }) : Promise.resolve({ ...mockGeneration, projectId, type: "video" as const }),
  generateAudio: (projectId: string, input: GenerateAudioRequest = {}) => isApiConfigured ? apiRequest<GenerationJob>(endpoints.projects.generateAudio(projectId), { method: "POST", body: input }) : Promise.resolve({ ...mockGeneration, projectId, type: "audio" as const }),
  getById: (id: string) => isApiConfigured ? apiRequest<GenerationJob>(endpoints.generations.byId(id)) : Promise.resolve({ ...mockGeneration, id }),
  retry: (id: string) => isApiConfigured ? apiRequest<GenerationJob>(endpoints.generations.retry(id), { method: "POST" }) : Promise.resolve({ ...mockGeneration, id, status: "queued" as const }),
};
