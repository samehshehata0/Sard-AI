import { BookOpen, FileText, HeartPulse, PlaySquare, Sparkles } from "lucide-react";
import { Card } from "@/components/ui/card";

const iconMap = {
  book: BookOpen,
  file: FileText,
  heart: HeartPulse,
  play: PlaySquare,
  sparkles: Sparkles,
};

export function ReportScoreCard({ label, value, icon }: { label: string; value: number; icon: keyof typeof iconMap }) {
  const Icon = iconMap[icon];

  return (
    <Card>
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-bold text-muted-foreground">{label}</p>
          <p className="mt-2 font-numbers text-3xl font-bold text-foreground">{value}%</p>
        </div>
        <div className="rounded-2xl bg-primary/10 p-3 text-primary">
          <Icon className="h-6 w-6" />
        </div>
      </div>
      <div className="mt-5 h-2 rounded-full bg-muted">
        <div className="h-2 rounded-full bg-gradient-to-l from-primary to-secondary" style={{ width: `${value}%` }} />
      </div>
    </Card>
  );
}
