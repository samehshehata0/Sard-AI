import type { PaginationParams } from "@/types/api";

export type RequestedOutput = "text" | "audio" | "video";
export type ProjectStatus = "draft" | "queued" | "processing" | "completed" | "failed" | "cancelled";

export interface Project {
  id: string;
  userId: string;
  title: string;
  educationalTopic: string;
  learningObjectives: string[];
  learnerAge: string;
  educationLevel: string;
  learnerCharacteristics: string;
  storyStyle: string;
  voiceTone: string;
  requestedOutputs: RequestedOutput[];
  prompt: string;
  status: ProjectStatus;
  videoUrl: string | null;
  audioUrl: string | null;
  thumbnailUrl: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface CreateProjectInput {
  title: string;
  educationalTopic: string;
  learningObjectives: string[];
  learnerAge: string;
  educationLevel: string;
  learnerCharacteristics: string;
  storyStyle: string;
  voiceTone: string;
  requestedOutputs: RequestedOutput[];
  prompt?: string;
}

export type UpdateProjectInput = Partial<CreateProjectInput>;

export interface ProjectListParams extends PaginationParams {
  status?: ProjectStatus;
  search?: string;
  sort?: "createdAt" | "updatedAt" | "title";
  order?: "asc" | "desc";
}

export interface ProjectCardView {
  id: string;
  title: string;
  topic: string;
  status: "مكتملة" | "مسودة" | "قيد المعالجة";
  date: string;
  quality: number;
  stage: string;
  duration: string;
  description: string;
}

export interface StoryEditorData {
  project: Project;
  storyContent: string;
  characters: string[];
  objectives: string[];
  suggestions: string[];
}

export interface StoryScene {
  number: number;
  title: string;
  visual: string;
  narration: string;
  prompt: string;
  status: "تم الإنشاء" | "يحتاج مراجعة" | "قيد الانتظار";
}
