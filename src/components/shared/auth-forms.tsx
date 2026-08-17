"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { useState } from "react";
import { z } from "zod";
import { BrandLogo } from "@/components/brand/brand-logo";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card } from "@/components/ui/card";
import { ApiError } from "@/lib/api/errors";
import { loginSchema, registerSchema } from "@/lib/validations";
import { authService } from "@/services/auth-service";

export function LoginForm() {
  const router = useRouter();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof loginSchema>>({ resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "" } });
  async function submit(values: z.infer<typeof loginSchema>) {
    setSubmitError(null);
    try {
      await authService.login(values);
      router.replace("/dashboard");
      router.refresh();
    } catch (error) {
      const hasFieldErrors = applyServerErrors(form.setError, ["email", "password"], error);
      setSubmitError(hasFieldErrors ? null : error instanceof Error ? error.message : "تعذر تسجيل الدخول.");
    }
  }
  return (
    <AuthFrame title="تسجيل الدخول" subtitle="مرحبًا بعودتك إلى مساحة القصص التعليمية">
      <form onSubmit={form.handleSubmit(submit)} className="space-y-4">
        <Field label="البريد الإلكتروني" error={form.formState.errors.email?.message}>
          <input {...form.register("email")} className="input" placeholder="أدخل بريدك الجامعي" />
        </Field>
        <Field label="كلمة المرور" error={form.formState.errors.password?.message}>
          <input {...form.register("password")} type="password" className="input" placeholder="أدخل كلمة المرور" />
        </Field>
        <div className="flex items-center justify-between gap-4 text-sm">
          <label className="inline-flex items-center gap-2 font-bold text-muted-foreground">
            <input type="checkbox" defaultChecked className="h-4 w-4 rounded border-border accent-primary" />
            تذكرني
          </label>
          <Link href="/login" className="font-bold text-primary">نسيت كلمة المرور؟</Link>
        </div>
        {submitError ? <p className="text-sm font-bold text-destructive" role="alert">{submitError}</p> : null}
        <ArabicButton className="w-full" type="submit" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? "جارٍ تسجيل الدخول..." : "تسجيل الدخول"}
        </ArabicButton>
        <p className="text-center text-sm text-muted-foreground">
          ليس لديك حساب؟ <Link href="/register" className="font-bold text-primary">إنشاء حساب جديد</Link>
        </p>
      </form>
    </AuthFrame>
  );
}

export function RegisterForm() {
  const router = useRouter();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof registerSchema>>({ resolver: zodResolver(registerSchema), defaultValues: { fullName: "", email: "", password: "", confirmPassword: "", role: "student_teacher" } });
  async function submit(values: z.infer<typeof registerSchema>) {
    setSubmitError(null);
    try {
      await authService.register(values);
      router.replace("/dashboard");
      router.refresh();
    } catch (error) {
      const hasFieldErrors = applyServerErrors(form.setError, ["fullName", "email", "password", "confirmPassword", "role"], error);
      setSubmitError(hasFieldErrors ? null : error instanceof Error ? error.message : "تعذر إنشاء الحساب.");
    }
  }
  return (
    <AuthFrame title="إنشاء حساب" subtitle="ابدأ بناء قصص عربية تعليمية مدعومة بالذكاء الاصطناعي">
      <form onSubmit={form.handleSubmit(submit)} className="space-y-4">
        <Field label="الاسم الكامل" error={form.formState.errors.fullName?.message}>
          <input {...form.register("fullName")} className="input" placeholder="اكتب اسمك الكامل" />
        </Field>
        <Field label="البريد الإلكتروني" error={form.formState.errors.email?.message}>
          <input {...form.register("email")} className="input" placeholder="أدخل بريدك الجامعي" />
        </Field>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="كلمة المرور" error={form.formState.errors.password?.message}>
            <input {...form.register("password")} type="password" className="input" placeholder="8 أحرف على الأقل" />
          </Field>
          <Field label="تأكيد كلمة المرور" error={form.formState.errors.confirmPassword?.message}>
            <input {...form.register("confirmPassword")} type="password" className="input" placeholder="أعد إدخال كلمة المرور" />
          </Field>
        </div>
        <Field label="الدور" error={form.formState.errors.role?.message}>
          <select {...form.register("role")} className="input">
            <option value="student_teacher">طالب معلم</option>
            <option value="faculty_member">عضو هيئة تدريس</option>
            <option value="supervisor">مشرف</option>
          </select>
        </Field>
        {submitError ? <p className="text-sm font-bold text-destructive" role="alert">{submitError}</p> : null}
        <ArabicButton className="w-full" type="submit" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? "جارٍ إنشاء الحساب..." : "إنشاء الحساب"}
        </ArabicButton>
        <p className="text-center text-sm text-muted-foreground">
          لديك حساب بالفعل؟ <Link href="/login" className="font-bold text-primary">تسجيل الدخول</Link>
        </p>
      </form>
    </AuthFrame>
  );
}

function applyServerErrors<FieldName extends string>(
  setError: (name: FieldName, error: { type: string; message: string }) => void,
  fields: readonly FieldName[],
  error: unknown,
): boolean {
  if (!(error instanceof ApiError)) return false;

  let applied = false;
  for (const field of fields) {
    const message = error.details[field];
    if (!message) continue;
    setError(field, { type: "server", message });
    applied = true;
  }
  return applied;
}

function AuthFrame({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-background px-4 py-8">
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-6xl items-center justify-center">
        <div className="grid w-full items-center gap-8 lg:grid-cols-[1fr_480px]">
          <div className="hidden lg:block">
            <BrandLogo />
            <h1 className="mt-10 max-w-xl font-heading text-5xl font-black leading-tight text-foreground">من الفكرة... إلى قصة تعليمية متكاملة</h1>
            <p className="mt-5 max-w-lg text-lg leading-8 text-muted-foreground">واجهة عربية هادئة تساعد الطالب المعلم على التخطيط، الكتابة، المراجعة، وتصدير القصة بثقة.</p>
          </div>
          <Card className="p-7 md:p-8">
            <div className="mb-7 text-center">
              <div className="mb-6 flex justify-center lg:hidden"><BrandLogo compact /></div>
              <h2 className="font-heading text-3xl font-black text-foreground">{title}</h2>
              <p className="mt-2 text-sm leading-7 text-muted-foreground">{subtitle}</p>
            </div>
            {children}
          </Card>
        </div>
      </div>
    </main>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-bold text-foreground">{label}</span>
      {children}
      {error ? <span className="mt-2 block text-sm font-bold text-destructive">{error}</span> : null}
    </label>
  );
}
