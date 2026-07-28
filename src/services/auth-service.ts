import { endpoints } from "@/lib/api/endpoints";
import { apiRequest, isApiConfigured } from "@/services/api-client";
import { mockUser } from "@/services/mock-data";
import type { AuthResponse, LoginRequest, RegisterRequest } from "@/types/auth";
import type { User } from "@/types/user";

export const authService = {
  register: (input: RegisterRequest) => isApiConfigured ? apiRequest<AuthResponse>(endpoints.auth.register, { method: "POST", body: input }) : Promise.resolve({ user: mockUser }),
  login: (input: LoginRequest) => isApiConfigured ? apiRequest<AuthResponse>(endpoints.auth.login, { method: "POST", body: input }) : Promise.resolve({ user: mockUser }),
  logout: () => isApiConfigured ? apiRequest<void>(endpoints.auth.logout, { method: "POST" }) : Promise.resolve(),
  me: (): Promise<User> => isApiConfigured ? apiRequest<User>(endpoints.auth.me) : Promise.resolve(mockUser),
};
