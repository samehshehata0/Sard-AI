import { endpoints } from "@/lib/api/endpoints";
import { apiRequest, apiRequestEnvelope, isApiConfigured } from "@/services/api-client";
import { mockEditorData, mockProjectCards, mockProjects, mockScenes } from "@/services/mock-data";
import type { ApiSuccess } from "@/types/api";
import type { CreateProjectInput, Project, ProjectCardView, ProjectListParams, StoryEditorData, StoryScene, UpdateProjectInput } from "@/types/project";

function queryString(params: ProjectListParams = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => value !== undefined && query.set(key, String(value)));
  return query.size ? `?${query}` : "";
}

export const projectsService = {
  create: (input: CreateProjectInput) => isApiConfigured ? apiRequest<Project>(endpoints.projects.collection, { method: "POST", body: input }) : Promise.resolve({ ...mockProjects[0], ...input, id: `mock-${Date.now()}` }),
  list: async (params: ProjectListParams = {}): Promise<ApiSuccess<Project[]>> => {
    if (isApiConfigured) return apiRequestEnvelope<Project[]>(`${endpoints.projects.collection}${queryString(params)}`);
    return { data: mockProjects, meta: { page: 1, pageSize: mockProjects.length, totalItems: mockProjects.length, totalPages: 1 } };
  },
  getById: (id: string) => isApiConfigured ? apiRequest<Project>(endpoints.projects.byId(id)) : Promise.resolve(mockProjects.find((project) => project.id === id) ?? mockProjects[0]),
  update: (id: string, input: UpdateProjectInput) => isApiConfigured ? apiRequest<Project>(endpoints.projects.byId(id), { method: "PATCH", body: input }) : Promise.resolve({ ...(mockProjects.find((project) => project.id === id) ?? mockProjects[0]), ...input }),
  remove: (id: string) => isApiConfigured ? apiRequest<void>(endpoints.projects.byId(id), { method: "DELETE" }) : Promise.resolve(),
  getCards: (): Promise<ProjectCardView[]> => Promise.resolve(mockProjectCards),
  getEditorData: (id: string): Promise<StoryEditorData> => Promise.resolve({ ...mockEditorData, project: mockProjects.find((project) => project.id === id) ?? mockEditorData.project }),
  getScenes: (id: string): Promise<StoryScene[]> => {
    void id;
    return Promise.resolve(mockScenes);
  },
};
