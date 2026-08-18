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

const personalInfoSchema = z.object({
  fullName: z.string().trim().min(2, "الاسم الكامل مطلوب").max(100).regex(/^[\p{L}\p{M}][\p{L}\p{M}\s.'’_-]*$/u, "الاسم يحتوي على رموز غير مسموحة"),
});

type Values = z.infer<typeof personalInfoSchema>;

export function PersonalInfoSection({ user }: { user: User }) {
  const router = useRouter();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(personalInfoSchema),
    defaultValues: { fullName: user.fullName },
  });

  async function submit(values: Values) {
    setSubmitError(null);
    try {
      await authService.updateProfile({ fullName: values.fullName });
      form.reset(values);
      router.refresh();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "تعذر حفظ البيانات الشخصية.");
    }
  }

  return (
    <Card>
      <h3 className="font-heading text-xl font-extrabold text-foreground">البيانات الشخصية</h3>
      <form onSubmit={form.handleSubmit(submit)} className="mt-5 grid gap-4 md:grid-cols-2">
        <label className="block">
          <span className="text-xs font-bold text-muted-foreground">الاسم الكامل</span>
          <input {...form.register("fullName")} className="input mt-2" />
          {form.formState.errors.fullName ? (
            <span className="mt-2 block text-sm font-bold text-destructive">{form.formState.errors.fullName.message}</span>
          ) : null}
        </label>
        <label className="block">
          <span className="text-xs font-bold text-muted-foreground">البريد الإلكتروني</span>
          <input value={user.email} disabled className="input mt-2 cursor-not-allowed opacity-70" />
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
