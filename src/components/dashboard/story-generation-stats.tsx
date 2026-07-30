"use client";

import { AlertCircle, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { StatCard } from "@/components/dashboard/stat-card";
import { Card } from "@/components/ui/card";

type Status = "queued" | "generating" | "completed" | "failed";

export function StoryGenerationStats() {
  const [statuses, setStatuses] = useState<Status[]>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    void fetch("/api/stories", { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !Array.isArray(payload.stories)) throw new Error(typeof payload.error === "string" ? payload.error : "تعذر تحميل إحصاءات القصص.");
        setStatuses(payload.stories.map((story: { status: Status }) => story.status));
      })
      .catch((fetchError) => setError(fetchError instanceof Error ? fetchError.message : "تعذر تحميل إحصاءات القصص."));
  }, []);

  if (error) return <Card className="md:col-span-2 xl:col-span-4"><div className="flex items-center gap-3 text-destructive"><AlertCircle className="h-5 w-5" />{error}</div></Card>;
  if (!statuses) return <Card className="md:col-span-2 xl:col-span-4"><div className="flex items-center gap-3 text-muted-foreground"><LoaderCircle className="h-5 w-5 animate-spin text-primary" />جارٍ حساب إحصاءات قصصك…</div></Card>;

  const total = statuses.length;
  const completed = statuses.filter((status) => status === "completed").length;
  const generating = statuses.filter((status) => status === "generating" || status === "queued").length;
  const failed = statuses.filter((status) => status === "failed").length;
  return <>{[
    { label: "إجمالي القصص", value: String(total), hint: "قصصك المحفوظة في MongoDB", color: "blue" },
    { label: "قصص مكتملة", value: String(completed), hint: "أصولها مرفوعة إلى ImageKit", color: "green" },
    { label: "قيد التوليد", value: String(generating), hint: "طلبات لها تقدم مباشر", color: "purple" },
    { label: "توقفت بخطأ", value: String(failed), hint: "راجع سجل التشخيص داخل القصة", color: "teal" },
  ].map((stat) => <StatCard key={stat.label} {...stat} />)}</>;
}
