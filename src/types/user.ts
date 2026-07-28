export type UserRole = "student_teacher" | "faculty_member" | "supervisor";

export interface User {
  id: string;
  fullName: string;
  email: string;
  role: UserRole;
  institution: string | null;
  avatarUrl: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface UpdateUserInput {
  fullName?: string;
  institution?: string | null;
  avatarUrl?: string | null;
}
