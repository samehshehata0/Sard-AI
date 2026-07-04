import dynamic from "next/dynamic";
import { FormSkeleton } from "@/components/shared/route-skeleton";

const RegisterForm = dynamic(() => import("@/components/shared/auth-forms").then((mod) => mod.RegisterForm), {
  loading: () => <FormSkeleton />,
});

export default function RegisterPage() {
  return <RegisterForm />;
}
