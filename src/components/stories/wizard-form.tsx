"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2, WandSparkles } from "lucide-react";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card } from "@/components/ui/card";
import { storyWizardSchema } from "@/lib/validations";
import { projectsService } from "@/services/projects-service";
import type { RequestedOutput } from "@/types/project";

type WizardValues = z.infer<typeof storyWizardSchema>;

const steps = ["بيانات القصة", "الأهداف التعليمية", "خصائص المتعلمين", "إعدادات الذكاء الاصطناعي", "مراجعة وتوليد"];

export function WizardForm() {
  const [step, setStep] = useState(0);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const form = useForm<WizardValues>({
    resolver: zodResolver(storyWizardSchema),
    defaultValues: {
      title: "رحلة قطرة ماء",
      topic: "أهمية الحفاظ على الماء",
      stage: "المرحلة الابتدائية",
      duration: "4 دقائق",
      objectives: ["أن يشرح المتعلم أهمية ترشيد استهلاك الماء."],
      age: "9-11 سنة",
      level: "متوسط",
      needs: "أمثلة بصرية وحوار قصير",
      style: "حواري",
      tone: "مشجعة",
      output: "نص + صوت + فيديو",
    },
  });
  const values = useWatch({ control: form.control });
  const objectives = values.objectives?.length ? values.objectives : [""];

  async function next() {
    const stepFields: (keyof WizardValues)[][] = [
      ["title", "topic", "stage", "duration"],
      ["objectives"],
      ["age", "level", "needs"],
      ["style", "tone", "output"],
      [],
    ];
    const ok = await form.trigger(stepFields[step]);
    if (ok) setStep((current) => Math.min(current + 1, steps.length - 1));
  }

  async function createProject(values: WizardValues) {
    const outputMap: Record<string, RequestedOutput[]> = {
      "نص فقط": ["text"],
      "نص + صوت": ["text", "audio"],
      "نص + صوت + فيديو": ["text", "audio", "video"],
    };
    setSubmitError(null);
    try {
      await projectsService.create({
        title: values.title,
        educationalTopic: values.topic,
        learningObjectives: values.objectives,
        learnerAge: values.age,
        educationLevel: values.stage,
        learnerCharacteristics: values.needs,
        storyStyle: values.style,
        voiceTone: values.tone,
        requestedOutputs: outputMap[values.output] ?? ["text"],
        prompt: `${values.topic} - ${values.duration} - مستوى ${values.level}`,
      });
      setStep(4);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "تعذر إنشاء المشروع.");
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
            className={`rounded-2xl px-3 py-3 text-sm font-bold transition ${index <= step ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}
          >
            {index + 1}. {label}
          </button>
        ))}
      </div>

      <form
        className="mt-8 space-y-6"
        onSubmit={form.handleSubmit(createProject)}
      >
        {step === 0 ? (
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="عنوان مبدئي" error={form.formState.errors.title?.message}>
              <input {...form.register("title")} className="input" placeholder="مثال: رحلة قطرة ماء" />
            </Field>
            <Field label="الموضوع التعليمي" error={form.formState.errors.topic?.message}>
              <input {...form.register("topic")} className="input" placeholder="مثال: أهمية الحفاظ على الماء" />
            </Field>
            <Field label="المرحلة التعليمية" error={form.formState.errors.stage?.message}>
              <select {...form.register("stage")} className="input">
                <option>المرحلة الابتدائية</option>
                <option>المرحلة المتوسطة</option>
                <option>المرحلة الثانوية</option>
              </select>
            </Field>
            <Field label="مدة القصة المتوقعة" error={form.formState.errors.duration?.message}>
              <select {...form.register("duration")} className="input">
                <option>3 دقائق</option>
                <option>4 دقائق</option>
                <option>5 دقائق</option>
                <option>7 دقائق</option>
              </select>
            </Field>
          </div>
        ) : null}

        {step === 1 ? (
          <div className="space-y-4">
            {objectives.map((_, index) => (
              <Field key={index} label={`هدف تعليمي ${index + 1}`} error={form.formState.errors.objectives?.[index]?.message}>
                <div className="flex gap-2">
                  <input {...form.register(`objectives.${index}`)} className="input" placeholder="اكتب هدفًا تعليميًا واضحًا" />
                  <button
                    type="button"
                    onClick={() => form.setValue("objectives", objectives.filter((_, itemIndex) => itemIndex !== index), { shouldValidate: true })}
                    className="rounded-2xl border border-border bg-card p-3 text-destructive"
                    aria-label="حذف الهدف"
                  >
                    <Trash2 className="h-5 w-5" />
                  </button>
                </div>
              </Field>
            ))}
            <ArabicButton type="button" variant="outline" onClick={() => form.setValue("objectives", [...objectives, ""], { shouldValidate: true })} icon={<Plus className="h-4 w-4" />}>
              إضافة هدف
            </ArabicButton>
            {typeof form.formState.errors.objectives?.message === "string" ? <p className="text-sm font-bold text-destructive">{form.formState.errors.objectives.message}</p> : null}
          </div>
        ) : null}

        {step === 2 ? (
          <div className="grid gap-4 md:grid-cols-3">
            <Field label="العمر" error={form.formState.errors.age?.message}>
              <input {...form.register("age")} className="input" placeholder="مثال: 9-11 سنة" />
            </Field>
            <Field label="المستوى" error={form.formState.errors.level?.message}>
              <input {...form.register("level")} className="input" placeholder="مثال: متوسط" />
            </Field>
            <Field label="الاحتياجات التعليمية" error={form.formState.errors.needs?.message}>
              <input {...form.register("needs")} className="input" placeholder="مثال: دعم بصري وحوار قصير" />
            </Field>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="grid gap-4 md:grid-cols-3">
            <Field label="أسلوب القصة" error={form.formState.errors.style?.message}>
              <select {...form.register("style")} className="input">
                {["مبسط", "حواري", "خيالي", "واقعي"].map((item) => <option key={item}>{item}</option>)}
              </select>
            </Field>
            <Field label="نبرة الصوت" error={form.formState.errors.tone?.message}>
              <select {...form.register("tone")} className="input">
                {["هادئة", "مشجعة", "حماسية"].map((item) => <option key={item}>{item}</option>)}
              </select>
            </Field>
            <Field label="نوع المخرجات" error={form.formState.errors.output?.message}>
              <select {...form.register("output")} className="input">
                {["نص فقط", "نص + صوت", "نص + صوت + فيديو"].map((item) => <option key={item}>{item}</option>)}
              </select>
            </Field>
          </div>
        ) : null}

        {step === 4 ? (
          <div className="rounded-3xl bg-muted p-6">
            <h3 className="font-heading text-xl font-extrabold text-foreground">ملخص القصة قبل التوليد</h3>
            <div className="mt-5 grid gap-3 md:grid-cols-2">
              <Summary label="العنوان" value={values.title} />
              <Summary label="الموضوع" value={values.topic} />
              <Summary label="المرحلة" value={values.stage} />
              <Summary label="المدة" value={values.duration} />
              <Summary label="الأسلوب" value={values.style} />
              <Summary label="المخرجات" value={values.output} />
            </div>
            {submitError ? <p className="mt-4 text-sm font-bold text-destructive" role="alert">{submitError}</p> : null}
            <ArabicButton className="mt-6" type="submit" disabled={form.formState.isSubmitting} icon={<WandSparkles className="h-4 w-4" />}>
              {form.formState.isSubmitting ? "جارٍ التوليد..." : "توليد القصة"}
            </ArabicButton>
          </div>
        ) : null}

        <div className="flex flex-wrap justify-between gap-3 border-t border-border pt-6">
          <ArabicButton type="button" variant="outline" onClick={() => setStep((current) => Math.max(current - 1, 0))} disabled={step === 0}>
            السابق
          </ArabicButton>
          {step < 4 ? (
            <ArabicButton type="button" onClick={next}>
              التالي
            </ArabicButton>
          ) : null}
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
