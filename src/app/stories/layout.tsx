import { ProtectedRoute } from "@/components/auth/protected-route";

export default function StoriesLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute>{children}</ProtectedRoute>;
}
