const encodeId = (id: string) => encodeURIComponent(id);

export const endpoints = {
  auth: {
    register: "/api/auth/register",
    login: "/api/auth/login",
    logout: "/api/auth/logout",
    me: "/api/auth/me",
    profile: "/api/auth/profile",
  },
  projects: {
    collection: "/api/projects",
    byId: (id: string) => `/api/projects/${encodeId(id)}`,
    generateVideo: (id: string) => `/api/projects/${encodeId(id)}/generate/video`,
    generateAudio: (id: string) => `/api/projects/${encodeId(id)}/generate/audio`,
    assessments: (id: string) => `/api/projects/${encodeId(id)}/assessments`,
    latestAssessment: (id: string) => `/api/projects/${encodeId(id)}/assessments/latest`,
    report: (id: string) => `/api/projects/${encodeId(id)}/report`,
  },
  generations: {
    byId: (id: string) => `/api/generations/${encodeId(id)}`,
    retry: (id: string) => `/api/generations/${encodeId(id)}/retry`,
  },
} as const;
