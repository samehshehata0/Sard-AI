"use client";

import { AlertCircle, CheckCircle2, ImageIcon, LoaderCircle, Mic2, RefreshCw, Video } from "lucide-react";
import Image from "next/image";
import { useEffect, useState } from "react";
import { Card, SectionTitle } from "@/components/ui/card";
import { ArabicButton } from "@/components/ui/arabic-button";
import type { GenerationLog, StoryAssets, StoryScene } from "@/lib/story-types";

type WorkspaceView = "storyboard" | "audio" | "video";

type WorkspaceStory = {
  _id: string;
  status: "queued" | "generating" | "completed" | "failed";
  progress: number;
  currentStep: string;
  error?: string;
  input: { title: string; speakerGender: "male" | "female"; tone: string };
  script?: string;
  sceneCount: number;
  scenes: StoryScene[];
  assets: StoryAssets;
  logs: GenerationLog[];
};

const copy: Record<WorkspaceView, { pageTitle: string; title: string; subtitle: string }> = {
  storyboard: {
    pageTitle: "اللوحات القصصية",
    title: "مساحة عمل القصة",
    subtitle: "تابع توليد صور المشاهد، النصوص، والحالة الفعلية لكل مشهد.",
  },
  audio: {
    pageTitle: "التعليق الصوتي",
    title: "التعليقات الصوتية للمشاهد",
    subtitle: "التعليق الموحد وملفات الصوت المنفصلة محفوظة هنا من دون دمجها مع الفيديو.",
  },
  video: {
    pageTitle: "الفيديو",
    title: "مقاطع الفيديو للمشاهد",
    subtitle: "شغّل الفيديو النهائي المرفق بالتعليق الصوتي، أو اعرض النسخة الصامتة ومقاطع المشاهد منفصلة.",
  },
};

function statusLabel(status: WorkspaceStory["status"]) {
  return ({ queued: "بانتظار بدء التوليد", generating: "جارٍ التوليد", completed: "اكتمل", failed: "توقف بسبب خطأ" })[status];
}

export function StoryWorkspace({ storyId, view }: { storyId: string; view: WorkspaceView }) {
  const [story, setStory] = useState<WorkspaceStory>();
  const [loadError, setLoadError] = useState<string>();
  const [refreshKey, setRefreshKey] = useState(0);
  const [isRetrying, setIsRetrying] = useState(false);
  const [isRebuildingVideo, setIsRebuildingVideo] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const load = async () => {
      try {
        const response = await fetch(`/api/stories/${storyId}`, { cache: "no-store" });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.story) throw new Error(typeof payload.error === "string" ? payload.error : "تعذر تحميل حالة القصة.");
        if (cancelled) return;
        const nextStory = payload.story as WorkspaceStory;
        setStory(nextStory);
        setLoadError(undefined);
        console.info(`[Sard][UI] تحديث حالة القصة: ${nextStory.status} (${nextStory.progress}%).`);
        if (nextStory.status === "queued" || nextStory.status === "generating") timer = setTimeout(load, 2_000);
      } catch (error) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "تعذر تحميل حالة القصة.";
          console.error("[Sard][UI] فشل تحميل مساحة العمل:", message);
          setLoadError(message);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [refreshKey, storyId]);

  async function retryGeneration() {
    setIsRetrying(true);
    setLoadError(undefined);
    try {
      const response = await fetch(`/api/stories/${storyId}/retry`, { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof payload.error === "string" ? payload.error : "تعذرت إعادة محاولة التوليد.");
      console.info(`[Sard][UI] أعيدت محاولة توليد القصة ${storyId}.`);
      setRefreshKey((value) => value + 1);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "تعذرت إعادة محاولة التوليد.");
    } finally {
      setIsRetrying(false);
    }
  }

  async function rebuildVideoDuration() {
    setIsRebuildingVideo(true);
    setLoadError(undefined);
    try {
      const response = await fetch(`/api/stories/${storyId}/video/rebuild`, { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof payload.error === "string" ? payload.error : "تعذر إصلاح مدة الفيديو.");
      console.info(`[Sard][UI] أُصلحت مدة فيديو القصة ${storyId}.`);
      setRefreshKey((value) => value + 1);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "تعذر إصلاح مدة الفيديو.");
    } finally {
      setIsRebuildingVideo(false);
    }
  }

  if (loadError) return <WorkspaceError message={loadError} />;
  if (!story) return <WorkspaceLoading />;

  const details = copy[view];
  return (
    <div className="space-y-6">
      <SectionTitle title={details.title} subtitle={details.subtitle} />
      <GenerationStatus story={story} onRetry={retryGeneration} isRetrying={isRetrying} />
      {view === "storyboard" ? <Storyboard story={story} /> : null}
      {view === "audio" ? <AudioWorkspace story={story} /> : null}
      {view === "video" ? <VideoWorkspace story={story} onRebuildDuration={rebuildVideoDuration} isRebuilding={isRebuildingVideo} /> : null}
      <GenerationLog logs={story.logs} />
    </div>
  );
}

function GenerationStatus({ story, onRetry, isRetrying }: { story: WorkspaceStory; onRetry: () => void; isRetrying: boolean }) {
  const isFailed = story.status === "failed";
  const complete = story.status === "completed";
  return (
    <Card className={isFailed ? "border-destructive/30" : ""}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          {isFailed ? <AlertCircle className="h-7 w-7 text-destructive" /> : complete ? <CheckCircle2 className="h-7 w-7 text-success" /> : <LoaderCircle className="h-7 w-7 animate-spin text-primary" />}
          <div>
            <p className="font-heading text-lg font-extrabold text-foreground">{story.input.title}</p>
            <p className={isFailed ? "mt-1 text-sm font-bold text-destructive" : "mt-1 text-sm font-bold text-muted-foreground"}>{isFailed ? story.error : story.currentStep}</p>
          </div>
        </div>
        <div className="flex items-center gap-3"><span className={`rounded-full px-4 py-2 text-sm font-bold ${isFailed ? "bg-destructive/10 text-destructive" : complete ? "bg-success/10 text-success" : "bg-primary/10 text-primary"}`}>{statusLabel(story.status)} · {story.progress}%</span>{isFailed ? <ArabicButton type="button" variant="outline" disabled={isRetrying} onClick={onRetry} icon={<RefreshCw className={`h-4 w-4 ${isRetrying ? "animate-spin" : ""}`} />}>{isRetrying ? "جارٍ إعادة المحاولة…" : "إعادة المحاولة"}</ArabicButton> : null}</div>
      </div>
      <div className="mt-5 h-3 overflow-hidden rounded-full bg-muted" aria-label={`التقدم ${story.progress}%`}>
        <div className={isFailed ? "h-full bg-destructive transition-all duration-500" : "h-full bg-gradient-to-l from-primary to-secondary transition-all duration-500"} style={{ width: `${story.progress}%` }} />
      </div>
      <p className="mt-3 text-xs font-bold text-muted-foreground">عدد المشاهد المخطط له: {story.sceneCount} من أصل 16 كحد أقصى — مدة كل مشهد بين 3 و5 ثوانٍ.</p>
    </Card>
  );
}

function Storyboard({ story }: { story: WorkspaceStory }) {
  return (
    <div className="space-y-5">
      {story.status === "completed" ? (
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h3 className="font-heading text-xl font-extrabold text-foreground">الأصول النهائية جاهزة</h3>
              <p className="mt-1 text-sm leading-7 text-muted-foreground">الفيديو النهائي يتضمن التعليق الصوتي، كما يبقى ملف الصوت الموحد ونسخة الفيديو الصامتة متاحين بشكل منفصل.</p>
            </div>
            <div className="flex flex-wrap gap-3">
              <ArabicButton href={`/stories/${story._id}/audio`} variant="outline" icon={<Mic2 className="h-4 w-4" />}>فتح الصوت</ArabicButton>
              <ArabicButton href={`/stories/${story._id}/video`} icon={<Video className="h-4 w-4" />}>فتح الفيديو</ArabicButton>
            </div>
          </div>
        </Card>
      ) : null}
      {story.script ? <Card><h3 className="font-heading text-xl font-extrabold text-foreground">السيناريو العربي</h3><p className="mt-4 whitespace-pre-wrap leading-8 text-muted-foreground">{story.script}</p></Card> : null}
      {story.scenes.map((scene) => (
        <Card key={scene.number}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><p className="text-sm font-bold text-primary">المشهد {scene.number}</p><h3 className="mt-1 font-heading text-xl font-extrabold text-foreground">{scene.title}</h3></div>
            <span className="rounded-full bg-muted px-3 py-1 text-xs font-bold text-muted-foreground">{scene.durationSeconds} ثوانٍ</span>
          </div>
          <div className="mt-5 grid gap-5 lg:grid-cols-[280px_1fr]">
            {scene.imageUrl ? <Image src={scene.imageUrl} alt={`صورة المشهد ${scene.number}: ${scene.title}`} width={1024} height={1024} className="aspect-square w-full rounded-2xl border border-border object-cover" /> : <div className="flex aspect-square items-center justify-center rounded-2xl bg-muted text-muted-foreground"><ImageIcon className="h-10 w-10" /></div>}
            <div className="space-y-4">
              <Info label="الوصف البصري" value={scene.visualDescription} />
              <Info label="النص الصوتي" value={scene.narration} />
              {scene.imagePrompt ? <Info label="مطالبة الصورة" value={scene.imagePrompt} /> : null}
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

function AudioWorkspace({ story }: { story: WorkspaceStory }) {
  return (
    <div className="space-y-5">
      {story.assets.combinedAudioUrl ? <MediaCard title="التعليق الصوتي الموحد" icon={<Mic2 className="h-5 w-5" />}><audio controls className="w-full" src={story.assets.combinedAudioUrl}>المتصفح لا يدعم تشغيل الصوت.</audio></MediaCard> : null}
      <div className="grid gap-5 md:grid-cols-2">
        {story.scenes.map((scene) => (
          <MediaCard key={scene.number} title={`التعليق الصوتي — المشهد ${scene.number}`} icon={<Mic2 className="h-5 w-5" />}>
            <p className="mb-4 text-sm leading-7 text-muted-foreground">{scene.narration}</p>
            {scene.audioUrl ? <audio controls className="w-full" src={scene.audioUrl}>المتصفح لا يدعم تشغيل الصوت.</audio> : <Waiting label="لم يُرفع ملف الصوت بعد." />}
          </MediaCard>
        ))}
      </div>
    </div>
  );
}

function VideoWorkspace({ story, onRebuildDuration, isRebuilding }: { story: WorkspaceStory; onRebuildDuration: () => void; isRebuilding: boolean }) {
  return (
    <div className="space-y-5">
      {story.status === "completed" ? (
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h3 className="font-heading text-lg font-extrabold text-foreground">تطابق مدة الفيديو</h3>
              <p className="mt-1 text-sm leading-7 text-muted-foreground">إذا أرجعت مساحة LTX مقاطع أقصر من مدة المشهد، أصلح المدة وادمج التعليق الصوتي من الملفات الموجودة دون إعادة توليد القصة.</p>
            </div>
            <ArabicButton type="button" variant="outline" disabled={isRebuilding} onClick={onRebuildDuration} icon={<RefreshCw className={`h-4 w-4 ${isRebuilding ? "animate-spin" : ""}`} />}>
              {isRebuilding ? "جارٍ إصلاح المدة والدمج…" : "إصلاح المدة ودمج الصوت"}
            </ArabicButton>
          </div>
        </Card>
      ) : null}
      {story.assets.combinedNarratedVideoUrl ? <MediaCard title="الفيديو النهائي مع التعليق الصوتي" icon={<Video className="h-5 w-5" />}><video controls preload="metadata" className="aspect-video w-full rounded-2xl bg-black" src={story.assets.combinedNarratedVideoUrl}>المتصفح لا يدعم تشغيل الفيديو.</video></MediaCard> : null}
      {story.assets.combinedVideoUrl ? <MediaCard title="الفيديو الموحد بلا تعليق صوتي" icon={<Video className="h-5 w-5" />}><video controls preload="metadata" className="aspect-video w-full rounded-2xl bg-black" src={story.assets.combinedVideoUrl}>المتصفح لا يدعم تشغيل الفيديو.</video></MediaCard> : null}
      <div className="grid gap-5 md:grid-cols-2">
        {story.scenes.map((scene) => (
          <MediaCard key={scene.number} title={`فيديو المشهد ${scene.number} — بلا صوت`} icon={<Video className="h-5 w-5" />}>
            {scene.videoUrl ? <video controls preload="metadata" className="aspect-video w-full rounded-2xl bg-black" src={scene.videoUrl}>المتصفح لا يدعم تشغيل الفيديو.</video> : <Waiting label="لم يُرفع فيديو هذا المشهد بعد." />}
          </MediaCard>
        ))}
      </div>
    </div>
  );
}

function MediaCard({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return <Card><div className="mb-4 flex items-center gap-2 text-primary">{icon}<h3 className="font-heading text-lg font-extrabold text-foreground">{title}</h3></div>{children}</Card>;
}

function Info({ label, value }: { label: string; value: string }) {
  return <div><p className="mb-1 text-xs font-bold text-muted-foreground">{label}</p><p className="rounded-2xl bg-muted p-3 text-sm leading-7 text-muted-foreground">{value}</p></div>;
}

function Waiting({ label }: { label: string }) {
  return <div className="flex min-h-24 items-center gap-3 rounded-2xl bg-muted p-4 text-sm font-bold text-muted-foreground"><LoaderCircle className="h-5 w-5 animate-spin text-primary" />{label}</div>;
}

function GenerationLog({ logs }: { logs: GenerationLog[] }) {
  return (
    <Card>
      <h3 className="font-heading text-lg font-extrabold text-foreground">سجل التشخيص المباشر</h3>
      <p className="mt-1 text-sm text-muted-foreground">تظهر نفس الأحداث في طرفية الخادم من دون كشف مفاتيح الوصول.</p>
      <div className="mt-4 max-h-72 space-y-2 overflow-y-auto rounded-2xl bg-slate-950 p-4 font-mono text-xs leading-6 text-slate-100" dir="rtl">
        {logs.length ? logs.slice().reverse().map((log, index) => <p key={`${String(log.at)}-${index}`} className={log.level === "error" ? "text-red-300" : "text-emerald-200"}>[{new Date(log.at).toLocaleTimeString("ar-JO")}] {log.message}</p>) : <p className="text-slate-300">لا توجد أحداث مسجلة حتى الآن.</p>}
      </div>
    </Card>
  );
}

function WorkspaceLoading() {
  return <Card><div className="flex items-center gap-3 text-muted-foreground"><LoaderCircle className="h-6 w-6 animate-spin text-primary" />جارٍ تحميل مساحة القصة…</div></Card>;
}

function WorkspaceError({ message }: { message: string }) {
  return <Card className="border-destructive/30"><div className="flex items-start gap-3"><AlertCircle className="mt-0.5 h-6 w-6 shrink-0 text-destructive" /><div><h2 className="font-heading text-xl font-extrabold text-foreground">تعذر فتح مساحة القصة</h2><p className="mt-2 leading-7 text-destructive">{message}</p></div></div></Card>;
}
