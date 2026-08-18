export type UserRole = "student_teacher" | "faculty_member" | "supervisor";
export type AuthenticatedUserRole = UserRole | "admin";

export interface User {
  id: string;
  fullName: string;
  email: string;
  role: AuthenticatedUserRole;
  institution: string | null;
  avatarUrl: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface UpdateUserInput {
  fullName?: string;
  institution?: string | null;
  avatarUrl?: string | null;
  role?: UserRole;
}
