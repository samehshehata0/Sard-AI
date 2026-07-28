import { endpoints } from "@/lib/api/endpoints";
import { apiRequest } from "@/services/api-client";
import type { AuthResponse, LoginRequest, RegisterRequest } from "@/types/auth";
import type { UpdateUserInput, User } from "@/types/user";

export const authService = {
  register: (input: RegisterRequest) => apiRequest<AuthResponse>(endpoints.auth.register, { method: "POST", body: input }),
  login: (input: LoginRequest) => apiRequest<AuthResponse>(endpoints.auth.login, { method: "POST", body: input }),
  logout: () => apiRequest<void>(endpoints.auth.logout, { method: "POST" }),
  me: (): Promise<User> => apiRequest<User>(endpoints.auth.me),
  updateProfile: (input: UpdateUserInput): Promise<User> => apiRequest<User>(endpoints.auth.profile, { method: "PATCH", body: input }),
};
