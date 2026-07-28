import { ProtectedRoute } from "@/components/auth/protected-route";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute>{children}</ProtectedRoute>;
}
