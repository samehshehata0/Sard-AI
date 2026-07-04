import { Download, RefreshCw, Video } from "lucide-react";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card } from "@/components/ui/card";

export function VideoPlayerCard() {
  return (
    <Card>
      <div className="flex aspect-video items-center justify-center rounded-3xl bg-gradient-to-br from-foreground to-primary text-background">
        <div className="text-center">
          <Video className="mx-auto h-16 w-16 text-background/70" />
          <p className="mt-4 font-heading text-2xl font-extrabold">معاينة الفيديو</p>
          <p className="mt-2 text-sm text-background/75">سيظهر الفيديو التعليمي بعد إنشاء المشاهد</p>
        </div>
      </div>
      <div className="mt-5 flex flex-wrap gap-3">
        <ArabicButton icon={<Video className="h-4 w-4" />}>إنشاء الفيديو</ArabicButton>
        <ArabicButton variant="outline" icon={<Download className="h-4 w-4" />}>تحميل الفيديو</ArabicButton>
        <ArabicButton variant="ghost" icon={<RefreshCw className="h-4 w-4" />}>إعادة التوليد</ArabicButton>
      </div>
    </Card>
  );
}
