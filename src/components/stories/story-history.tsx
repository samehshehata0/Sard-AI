"use client";

import { AlertCircle, LoaderCircle, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { EmptyState } from "@/components/shared/empty-state";
import { Card } from "@/components/ui/card";

type StorySummary = {
  _id: string;
  status: "queued" | "generating" | "completed" | "failed";
  progress: number;
  currentStep: string;
  error?: string;
  sceneCount: number;
  input: { title: string; topic: string; duration: string };
  createdAt: string;
};

const filters = [
  { value: "all", label: "الكل" },
  { value: "completed", label: "مكتملة" },
  { value: "generating", label: "قيد التوليد" },
  { value: "failed", label: "توقفت بخطأ" },
] as const;

function statusLabel(status: StorySummary["status"]) {
  return ({ queued: "بانتظار التنفيذ", generating: "قيد التوليد", completed: "مكتملة", failed: "توقفت بخطأ" })[status];
}

export function StoryHistory({ limit }: { limit?: number }) {
  const [stories, setStories] = useState<StorySummary[]>([]);
  const [filter, setFilter] = useState<(typeof filters)[number]["value"]>("all");
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string>();

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch("/api/stories", { cache: "no-store" });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !Array.isArray(payload.stories)) throw new Error(typeof payload.error === "string" ? payload.error : "تعذر تحميل سجل القصص.");
        setStories(payload.stories);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "تعذر تحميل سجل القصص.");
      } finally {
        setIsLoading(false);
      }
    };
    void load();
  }, []);

  const visibleStories = useMemo(() => stories.filter((story) => {
    const matchesFilter = filter === "all" || story.status === filter || (filter === "generating" && story.status === "queued");
    const haystack = `${story.input.title} ${story.input.topic}`.toLocaleLowerCase("ar");
    return matchesFilter && haystack.includes(query.trim().toLocaleLowerCase("ar"));
  }).slice(0, limit), [filter, limit, query, stories]);

  if (isLoading) return <Card><div className="flex items-center gap-3 text-muted-foreground"><LoaderCircle className="h-5 w-5 animate-spin text-primary" />جارٍ تحميل قصصك من MongoDB…</div></Card>;
  if (error) return <Card className="border-destructive/30"><div className="flex items-start gap-3 text-destructive"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />{error}</div></Card>;

  return (
    <div className="space-y-5">
      {!limit ? <div className="flex flex-col gap-3 rounded-3xl border border-border bg-card p-4 shadow-sm md:flex-row md:items-center md:justify-between"><div className="flex flex-wrap gap-2">{filters.map((item) => <button key={item.value} type="button" onClick={() => setFilter(item.value)} className={`rounded-full px-4 py-2 text-sm font-bold ${filter === item.value ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-primary/10 hover:text-primary"}`}>{item.label}</button>)}</div><label className="flex items-center gap-2 rounded-2xl border border-border px-4 py-3 md:w-80"><Search className="h-5 w-5 text-muted-foreground" /><input value={query} onChange={(event) => setQuery(event.target.value)} className="w-full bg-transparent text-sm outline-none" placeholder="ابحث باسم القصة أو فكرتها" /></label></div> : null}
      {visibleStories.length ? <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{visibleStories.map((story) => <StorySummaryCard key={story._id} story={story} />)}</div> : <EmptyState title="لا توجد قصص مطابقة" description="ستظهر هنا القصص التي تنشئها من هذه المتصفح بعد حفظها في MongoDB." />}
    </div>
  );
}

function StorySummaryCard({ story }: { story: StorySummary }) {
  const failed = story.status === "failed";
  const statusClass = failed ? "bg-destructive/10 text-destructive" : story.status === "completed" ? "bg-success/10 text-success" : "bg-primary/10 text-primary";
  return <Card className="flex h-full flex-col"><div className="flex items-start justify-between gap-3"><div><h3 className="font-heading text-xl font-extrabold text-foreground">{story.input.title}</h3><p className="mt-1 text-sm font-bold text-primary">{story.input.topic}</p></div><span className={`shrink-0 rounded-full px-3 py-1 text-xs font-bold ${statusClass}`}>{statusLabel(story.status)}</span></div><p className={failed ? "mt-4 flex-1 text-sm leading-7 text-destructive" : "mt-4 flex-1 text-sm leading-7 text-muted-foreground"}>{failed ? story.error : story.currentStep}</p><div className="mt-5 h-2 overflow-hidden rounded-full bg-muted"><div className={failed ? "h-full bg-destructive" : "h-full bg-primary"} style={{ width: `${story.progress}%` }} /></div><div className="mt-4 flex items-center justify-between text-xs font-bold text-muted-foreground"><span>{story.input.duration} · {story.sceneCount} مشاهد</span><span>{new Date(story.createdAt).toLocaleDateString("ar-JO")}</span></div><Link href={`/stories/${story._id}/storyboard`} className="mt-5 inline-flex font-bold text-primary hover:opacity-80">فتح مساحة القصة</Link></Card>;
}
