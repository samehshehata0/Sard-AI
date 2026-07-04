import dynamic from "next/dynamic";
import { FormSkeleton } from "@/components/shared/route-skeleton";

const LoginForm = dynamic(() => import("@/components/shared/auth-forms").then((mod) => mod.LoginForm), {
  loading: () => <FormSkeleton />,
});

export default function LoginPage() {
  return <LoginForm />;
}
