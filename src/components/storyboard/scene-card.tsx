import { Edit3, Mic2, Video } from "lucide-react";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card } from "@/components/ui/card";

const statusClass: Record<string, string> = {
  "تم الإنشاء": "bg-success/10 text-success",
  "يحتاج مراجعة": "bg-warning/10 text-warning",
  "قيد الانتظار": "bg-muted text-muted-foreground",
};

export function SceneCard({ scene }: { scene: { number: number; title: string; visual: string; narration: string; prompt: string; status: string } }) {
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-primary">رقم المشهد {scene.number}</p>
          <h3 className="mt-1 font-heading text-xl font-extrabold text-foreground">{scene.title}</h3>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-bold ${statusClass[scene.status]}`}>الحالة: {scene.status}</span>
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <Info label="وصف بصري" value={scene.visual} />
        <Info label="النص الصوتي" value={scene.narration} />
        <Info label="Prompt الصورة/الفيديو" value={scene.prompt} wide />
      </div>
      <div className="mt-5 flex flex-wrap gap-3">
        <ArabicButton variant="outline" icon={<Edit3 className="h-4 w-4" />}>تعديل</ArabicButton>
        <ArabicButton variant="outline" icon={<Video className="h-4 w-4" />}>إنشاء فيديو</ArabicButton>
        <ArabicButton variant="outline" icon={<Mic2 className="h-4 w-4" />}>إنشاء صوت</ArabicButton>
      </div>
    </Card>
  );
}

function Info({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={wide ? "md:col-span-2" : ""}>
      <p className="mb-2 text-xs font-bold text-muted-foreground">{label}</p>
      <p className="rounded-2xl bg-muted p-4 text-sm leading-7 text-muted-foreground">{value}</p>
    </div>
  );
}
