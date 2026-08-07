"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { LoaderCircle, Plus, Trash2, WandSparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card } from "@/components/ui/card";
import { storyGenerationSchema } from "@/lib/story-request-schema";

type WizardValues = z.infer<typeof storyGenerationSchema>;

const steps = ["بيانات القصة", "الأهداف التعليمية", "خصائص المتعلمين", "إعدادات التوليد", "مراجعة وتوليد"];

export function WizardForm() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [requestError, setRequestError] = useState<string>();
  const form = useForm<WizardValues>({
    resolver: zodResolver(storyGenerationSchema),
    defaultValues: {
      title: "رحلة قطرة ماء",
      topic: "أهمية الحفاظ على الماء",
      stage: "المرحلة الابتدائية",
      objectives: ["أن يشرح المتعلم أهمية ترشيد استهلاك الماء."],
      age: "9-11 سنة",
      level: "متوسط",
      needs: "أمثلة بصرية وحوار قصير",
      style: "حواري",
      tone: "مشجعة",
      output: "نص + صوت + فيديو",
      speakerGender: "male",
    },
  });
  const values = useWatch({ control: form.control });
  const objectives = values.objectives?.length ? values.objectives : [""];

  async function next() {
    const stepFields: (keyof WizardValues)[][] = [
      ["title", "topic", "stage"],
      ["objectives"],
      ["age", "level", "needs"],
      ["style", "tone", "output", "speakerGender"],
      [],
    ];
    const ok = await form.trigger(stepFields[step]);
    if (ok) setStep((current) => Math.min(current + 1, steps.length - 1));
  }

  async function startGeneration(data: WizardValues) {
    setRequestError(undefined);
    setIsSubmitting(true);
    console.info("[Sard][UI] إرسال طلب إنشاء القصة.");
    try {
      const response = await fetch("/api/stories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || typeof payload.storyId !== "string") {
        throw new Error(typeof payload.error === "string" ? payload.error : "لم يبدأ طلب التوليد. راجع طرفية الخادم للتفاصيل.");
      }
      console.info(`[Sard][UI] بدأ التوليد للقصة ${payload.storyId}.`);
      router.push(`/stories/${payload.storyId}/storyboard`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "حدث خطأ غير معروف عند بدء التوليد.";
      console.error("[Sard][UI] فشل بدء التوليد:", message);
      setRequestError(message);
      setIsSubmitting(false);
    }
  }

  return (
    <Card>
      <div className="grid gap-3 md:grid-cols-5">
        {steps.map((label, index) => (
          <button
            key={label}
            type="button"
            onClick={() => setStep(index)}
            disabled={isSubmitting}
            className={`rounded-2xl px-3 py-3 text-sm font-bold transition ${index <= step ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}
          >
            {index + 1}. {label}
          </button>
        ))}
      </div>

      <form className="mt-8 space-y-6" onSubmit={form.handleSubmit(startGeneration)}>
        {step === 0 ? (
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="اسم القصة" error={form.formState.errors.title?.message}>
              <input {...form.register("title")} className="input" placeholder="مثال: رحلة قطرة ماء في الدورة الطبيعية" disabled={isSubmitting} />
            </Field>

            <Field label="المرحلة التعليمية" error={form.formState.errors.stage?.message}>
              <select {...form.register("stage")} className="input" disabled={isSubmitting}>
                <option>المرحلة الابتدائية</option>
                <option>المرحلة المتوسطة</option>
                <option>المرحلة الثانوية</option>
              </select>
            </Field>

            <div className="md:col-span-2 space-y-4">
              <Field label="فكرة القصة والتفاصيل الكاملة" error={form.formState.errors.topic?.message}>
                <textarea
                  {...form.register("topic")}
                  rows={4}
                  className="input min-h-[120px] py-3 leading-relaxed"
                  placeholder="اكتب فكرة القصة، السيناريو، الأحداث، الشخصيات، التحديات، أو أي تفاصيل ورؤية كاملة ترغب في أن يعتمد عليها الذكاء الاصطناعي بكامل الحرية..."
                  disabled={isSubmitting}
                />
              </Field>

              <Field label="توجيهات وتفاصيل خاصة للمحرك (اختياري)" error={form.formState.errors.custom_instructions?.message}>
                <textarea
                  {...form.register("custom_instructions")}
                  rows={2}
                  className="input min-h-[70px] py-3 leading-relaxed"
                  placeholder="مثال: ركز على الحوارات الكوميدية، استخدم شخصيات من الأطفال، أضف تساؤلات تفاعلية..."
                  disabled={isSubmitting}
                />
              </Field>
            </div>
            <div className="rounded-2xl border border-primary/20 bg-primary/5 p-5 md:col-span-2 flex items-center gap-4">
              <div className="text-3xl">✨</div>
              <div>
                <div className="text-sm font-extrabold text-foreground">عرض تقديمي وإنفوجرافيك بلا حدود</div>
                <div className="text-xs font-bold text-muted-foreground mt-1">تم إلغاء التحديد الزمني؛ يتم توليد عدد الشرائح ومحتوى الإنفوجرافيك ديناميكياً وبشكل غير محدود حسب أهداف القصة والدرس.</div>
              </div>
            </div>
          </div>
        ) : null}

        {step === 1 ? (
          <div className="space-y-4">
            {objectives.map((_, index) => (
              <Field key={index} label={`هدف تعليمي ${index + 1}`} error={form.formState.errors.objectives?.[index]?.message}>
                <div className="flex gap-2">
                  <input {...form.register(`objectives.${index}`)} className="input" placeholder="اكتب هدفاً تعليمياً واضحاً" disabled={isSubmitting} />
                  <button
                    type="button"
                    disabled={isSubmitting || objectives.length === 1}
                    onClick={() => form.setValue("objectives", objectives.filter((_, itemIndex) => itemIndex !== index), { shouldValidate: true })}
                    className="rounded-2xl border border-border bg-card p-3 text-destructive disabled:opacity-50"
                    aria-label="حذف الهدف"
                  >
                    <Trash2 className="h-5 w-5" />
                  </button>
                </div>
              </Field>
            ))}
            <ArabicButton type="button" variant="outline" disabled={isSubmitting} onClick={() => form.setValue("objectives", [...objectives, ""], { shouldValidate: true })} icon={<Plus className="h-4 w-4" />}>
              إضافة هدف
            </ArabicButton>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="grid gap-4 md:grid-cols-3">
            <Field label="العمر" error={form.formState.errors.age?.message}>
              <input {...form.register("age")} className="input" placeholder="مثال: 9-11 سنة" disabled={isSubmitting} />
            </Field>
            <Field label="المستوى" error={form.formState.errors.level?.message}>
              <input {...form.register("level")} className="input" placeholder="مثال: متوسط" disabled={isSubmitting} />
            </Field>
            <Field label="الاحتياجات التعليمية" error={form.formState.errors.needs?.message}>
              <input {...form.register("needs")} className="input" placeholder="مثال: دعم بصري وحوار قصير" disabled={isSubmitting} />
            </Field>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="أسلوب القصة" error={form.formState.errors.style?.message}>
              <select {...form.register("style")} className="input" disabled={isSubmitting}>
                {["مبسط", "حواري", "خيالي", "واقعي"].map((item) => <option key={item}>{item}</option>)}
              </select>
            </Field>
            <Field label="نبرة الصوت" error={form.formState.errors.tone?.message}>
              <select {...form.register("tone")} className="input" disabled={isSubmitting}>
                {["هادئة", "مشجعة", "حماسية"].map((item) => <option key={item}>{item}</option>)}
              </select>
            </Field>
            <Field label="نوع المخرجات" error={form.formState.errors.output?.message}>
              <select {...form.register("output")} className="input" disabled={isSubmitting}>
                {["نص فقط", "نص + صوت", "نص + صوت + فيديو"].map((item) => <option key={item}>{item}</option>)}
              </select>
            </Field>
            <Field label="جنس الراوي" error={form.formState.errors.speakerGender?.message}>
              <select {...form.register("speakerGender")} className="input" disabled={isSubmitting}>
                <option value="male">ذكر</option>
                <option value="female">أنثى</option>
              </select>
            </Field>
          </div>
        ) : null}

        {step === 4 ? (
          <div className="rounded-3xl bg-muted p-6">
            <h3 className="font-heading text-xl font-extrabold text-foreground">ملخص القصة قبل التوليد</h3>
            <div className="mt-5 grid gap-3 md:grid-cols-2">
              <Summary label="العنوان" value={values.title} />
              <Summary label="الفكرة" value={values.topic} />
              <Summary label="المرحلة" value={values.stage} />
              <Summary label="الأسلوب" value={values.style} />
              <Summary label="جنس الراوي" value={values.speakerGender === "female" ? "أنثى" : "ذكر"} />
            </div>
            {requestError ? <p role="alert" className="mt-5 rounded-2xl bg-destructive/10 p-4 text-sm font-bold text-destructive">{requestError}</p> : null}
            <ArabicButton className="mt-6" type="submit" disabled={isSubmitting} icon={isSubmitting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <WandSparkles className="h-4 w-4" />}>
              {isSubmitting ? "جارٍ بدء التوليد…" : "توليد القصة"}
            </ArabicButton>
          </div>
        ) : null}

        <div className="flex flex-wrap justify-between gap-3 border-t border-border pt-6">
          <ArabicButton type="button" variant="outline" disabled={step === 0 || isSubmitting} onClick={() => setStep((current) => Math.max(current - 1, 0))}>
            السابق
          </ArabicButton>
          {step < 4 ? <ArabicButton type="button" disabled={isSubmitting} onClick={next}>التالي</ArabicButton> : null}
        </div>
      </form>
    </Card>
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

function Summary({ label, value }: { label: string; value?: string }) {
  return (
    <div className="rounded-2xl bg-card p-4">
      <p className="text-xs font-bold text-muted-foreground">{label}</p>
      <p className="mt-1 font-bold text-foreground">{value}</p>
    </div>
  );
}
