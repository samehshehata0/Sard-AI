import { ProtectedRoute } from "@/components/auth/protected-route";

export default function HistoryLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute>{children}</ProtectedRoute>;
}
