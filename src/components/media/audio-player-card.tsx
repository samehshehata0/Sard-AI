import { Download, Mic2, Play, SlidersHorizontal } from "lucide-react";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card } from "@/components/ui/card";

export function AudioPlayerCard() {
  return (
    <Card>
      <div className="rounded-3xl bg-gradient-to-l from-accent/10 to-primary/10 p-6">
        <div className="flex items-center gap-4">
          <button className="rounded-full bg-primary p-4 text-primary-foreground" aria-label="تشغيل">
            <Play className="h-6 w-6 fill-current" />
          </button>
          <div className="h-3 flex-1 rounded-full bg-card">
            <div className="h-3 w-2/5 rounded-full bg-gradient-to-l from-accent to-primary" />
          </div>
          <span className="font-numbers text-sm font-bold text-muted-foreground">01:24</span>
        </div>
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-3">
        {["نوع الصوت: عربي هادئ", "السرعة: متوسطة", "النبرة: مشجعة"].map((item) => (
          <div key={item} className="rounded-2xl bg-muted p-4 text-sm font-bold text-muted-foreground">
            {item}
          </div>
        ))}
      </div>
      <div className="mt-5 flex flex-wrap gap-3">
        <ArabicButton icon={<Mic2 className="h-4 w-4" />}>إنشاء التعليق الصوتي</ArabicButton>
        <ArabicButton variant="outline" icon={<Download className="h-4 w-4" />}>تحميل الصوت</ArabicButton>
        <ArabicButton variant="ghost" icon={<SlidersHorizontal className="h-4 w-4" />}>ضبط الصوت</ArabicButton>
      </div>
    </Card>
  );
}
