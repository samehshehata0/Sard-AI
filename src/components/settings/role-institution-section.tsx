"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Save, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { authService } from "@/services/auth-service";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card } from "@/components/ui/card";
import type { User } from "@/types/user";

const roleOptions = [
  { value: "student_teacher", label: "طالب معلم" },
  { value: "faculty_member", label: "عضو هيئة تدريس" },
  { value: "supervisor", label: "مشرف" },
] as const;

const roleInstitutionSchema = z.object({
  role: z.enum(["student_teacher", "faculty_member", "supervisor"], { message: "الدور غير صالح" }),
  institution: z.string().trim().max(150, "اسم المؤسسة طويل جدًا"),
});

type Values = z.infer<typeof roleInstitutionSchema>;

export function RoleInstitutionSection({ user }: { user: User }) {
  const router = useRouter();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const isAdmin = user.role === "admin";
  const form = useForm<Values>({
    resolver: zodResolver(roleInstitutionSchema),
    defaultValues: { role: user.role === "admin" ? "student_teacher" : user.role, institution: user.institution ?? "" },
  });

  if (isAdmin) {
    return (
      <Card>
        <h3 className="font-heading text-xl font-extrabold text-foreground">الدور والمؤسسة</h3>
        <p className="mt-2 text-sm text-muted-foreground">حسابات مديري النظام لا يمكنها تغيير الدور من هذه الصفحة.</p>
      </Card>
    );
  }

  async function submit(values: Values) {
    setSubmitError(null);
    try {
      await authService.updateProfile({ role: values.role, institution: values.institution || null });
      form.reset(values);
      router.refresh();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "تعذر حفظ الدور والمؤسسة.");
    }
  }

  return (
    <Card>
      <h3 className="font-heading text-xl font-extrabold text-foreground">الدور والمؤسسة</h3>
      <form onSubmit={form.handleSubmit(submit)} className="mt-5 grid gap-4 md:grid-cols-2">
        <label className="block">
          <span className="text-xs font-bold text-muted-foreground">الدور</span>
          <select {...form.register("role")} className="input mt-2">
            {roleOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-xs font-bold text-muted-foreground">المؤسسة</span>
          <input {...form.register("institution")} className="input mt-2" />
          {form.formState.errors.institution ? (
            <span className="mt-2 block text-sm font-bold text-destructive">{form.formState.errors.institution.message}</span>
          ) : null}
        </label>
        {submitError ? <p className="text-sm font-bold text-destructive md:col-span-2" role="alert">{submitError}</p> : null}
        {form.formState.isDirty ? (
          <div className="flex gap-2 md:col-span-2">
            <ArabicButton type="submit" disabled={form.formState.isSubmitting} icon={<Save className="h-4 w-4" />}>
              {form.formState.isSubmitting ? "جارٍ الحفظ..." : "حفظ"}
            </ArabicButton>
            <ArabicButton
              type="button"
              variant="ghost"
              disabled={form.formState.isSubmitting}
              onClick={() => {
                form.reset();
                setSubmitError(null);
              }}
              icon={<X className="h-4 w-4" />}
            >
              تراجع
            </ArabicButton>
          </div>
        ) : null}
      </form>
    </Card>
  );
}
