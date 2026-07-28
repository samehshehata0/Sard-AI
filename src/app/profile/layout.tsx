import { ProtectedRoute } from "@/components/auth/protected-route";

export default function ProfileLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute>{children}</ProtectedRoute>;
}
