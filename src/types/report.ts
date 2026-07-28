export interface Report {
  id: string;
  projectId: string;
  progressScore: number;
  wellBeingScore: number;
  recommendations: string[];
  createdAt: string;
}

export interface ReportScore {
  label: string;
  value: number;
  icon: "book" | "sparkles" | "play" | "file" | "heart";
}

export interface ReportView extends Report {
  overall: number;
  scores: ReportScore[];
  strengths: string[];
  improvements: string[];
}
