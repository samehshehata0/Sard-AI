import type { User, UserRole } from "@/types/user";

export interface RegisterRequest {
  fullName: string;
  email: string;
  password: string;
  role: UserRole;
  institution?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
  remember?: boolean;
}

export interface AuthResponse {
  user: User;
  accessToken?: string;
}
