export type GenerationType = "video" | "audio";
export type GenerationStatus = "queued" | "processing" | "completed" | "failed" | "cancelled";

export interface GenerationJob {
  id: string;
  projectId: string;
  type: GenerationType;
  provider: string;
  providerJobId: string | null;
  status: GenerationStatus;
  outputUrl: string | null;
  errorMessage: string | null;
  createdAt: string;
  completedAt: string | null;
}

export interface GenerateVideoRequest {
  prompt?: string;
  aspectRatio?: "16:9" | "9:16" | "1:1";
}

export interface GenerateAudioRequest {
  prompt?: string;
  voice?: string;
  speed?: number;
  tone?: string;
}
