export type SpeakerGender = "male" | "female";

export type StoryInput = {
  title: string;
  topic: string;
  stage: string;
  duration: string;
  objectives: string[];
  age: string;
  level: string;
  needs: string;
  style: string;
  tone: string;
  output: string;
  speakerGender: SpeakerGender;
};

export type StoryScene = {
  number: number;
  title: string;
  durationSeconds: number;
  narration: string;
  narrationVocalized?: boolean;
  visualDescription: string;
  imagePrompt: string;
  imageGenerationPrompt?: string;
  videoPrompt: string;
  imageUrl?: string;
  audioUrl?: string;
  audioDurationMatched?: boolean;
  videoUrl?: string;
  videoGenerator?: "zerogpu-wan2.2-i2v" | "openrouter-seedance-2.0";
  error?: string;
};

export type GenerationLog = {
  at: Date;
  level: "info" | "error";
  message: string;
};

export type StoryAssets = {
  combinedAudioUrl?: string;
  combinedVideoUrl?: string;
  combinedNarratedVideoUrl?: string;
};

export type StoryDocument = {
  _id: string;
  userId: string;
  input: StoryInput;
  status: "queued" | "generating" | "completed" | "failed";
  progress: number;
  currentStep: string;
  error?: string;
  totalDurationSeconds: number;
  sceneCount: number;
  script?: string;
  characters?: Array<{ name: string; description: string }>;
  visualStyleGuide?: string;
  scenes: StoryScene[];
  assets: StoryAssets;
  logs: GenerationLog[];
  createdAt: Date;
  updatedAt: Date;
  completedAt?: Date;
};
