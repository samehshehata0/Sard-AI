export type AssessmentAnswer = number;

export interface Assessment {
  id: string;
  projectId: string;
  userId: string;
  stressAnswers: AssessmentAnswer[];
  motivationAnswers: AssessmentAnswer[];
  stressScore: number;
  motivationScore: number;
  wellBeingScore: number;
  createdAt: string;
}

export interface CreateAssessmentInput {
  stressAnswers: AssessmentAnswer[];
  motivationAnswers: AssessmentAnswer[];
}
