"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Edit3, Save, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { authService } from "@/services/auth-service";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card } from "@/components/ui/card";
import type { User } from "@/types/user";

const profileSchema = z.object({
  fullName: z.string().trim().min(2, "الاسم الكامل مطلوب").max(100).regex(/^[\p{L}\p{M}][\p{L}\p{M}\s.'’_-]*$/u, "الاسم يحتوي على رموز غير مسموحة"),
  institution: z.string().trim().max(150, "اسم المؤسسة طويل جدًا"),
});

type ProfileValues = z.infer<typeof profileSchema>;

const roleLabels = {
  student_teacher: "طالب معلم",
  faculty_member: "عضو هيئة تدريس",
  supervisor: "مشرف",
  admin: "مدير النظام",
};

export function ProfileForm({ user }: { user: User }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const form = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: { fullName: user.fullName, institution: user.institution ?? "" },
  });

  async function submit(values: ProfileValues) {
    setSubmitError(null);
    try {
      await authService.updateProfile({
        fullName: values.fullName,
        institution: values.institution || null,
      });
      setEditing(false);
      router.refresh();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "تعذر تحديث الملف الشخصي.");
    }
  }

  return (
    <Card>
      <form onSubmit={form.handleSubmit(submit)}>
        <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-l from-primary to-secondary font-heading text-2xl font-black text-primary-foreground">
              {user.fullName.trim().charAt(0)}
            </div>
            <div>
              {editing ? (
                <div>
                  <input {...form.register("fullName")} className="input text-xl font-extrabold" aria-label="الاسم الكامل" />
                  {form.formState.errors.fullName ? <p className="mt-2 text-sm font-bold text-destructive">{form.formState.errors.fullName.message}</p> : null}
                </div>
              ) : (
                <h2 className="font-heading text-2xl font-black text-foreground">{user.fullName}</h2>
              )}
              <p className="mt-1 text-sm font-bold text-muted-foreground">{roleLabels[user.role]}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {editing ? (
              <>
                <ArabicButton type="submit" disabled={form.formState.isSubmitting} icon={<Save className="h-4 w-4" />}>
                  {form.formState.isSubmitting ? "جارٍ الحفظ..." : "حفظ التعديلات"}
                </ArabicButton>
                <ArabicButton type="button" variant="ghost" onClick={() => setEditing(false)} icon={<X className="h-4 w-4" />}>إلغاء</ArabicButton>
              </>
            ) : (
              <ArabicButton type="button" onClick={() => setEditing(true)} icon={<Edit3 className="h-4 w-4" />}>تعديل الملف الشخصي</ArabicButton>
            )}
          </div>
        </div>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          <Info label="البريد الإلكتروني" value={user.email} />
          <Info label="الدور" value={roleLabels[user.role]} />
          {editing ? (
            <label className="rounded-2xl bg-muted p-4">
              <span className="text-xs font-bold text-muted-foreground">المؤسسة</span>
              <input {...form.register("institution")} className="input mt-2" />
              {form.formState.errors.institution ? <span className="mt-2 block text-sm font-bold text-destructive">{form.formState.errors.institution.message}</span> : null}
            </label>
          ) : (
            <Info label="المؤسسة" value={user.institution ?? "—"} />
          )}
        </div>
        {submitError ? <p className="mt-4 text-sm font-bold text-destructive" role="alert">{submitError}</p> : null}
      </form>
    </Card>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-muted p-4">
      <p className="text-xs font-bold text-muted-foreground">{label}</p>
      <p className="mt-2 font-bold text-foreground">{value}</p>
    </div>
  );
}
