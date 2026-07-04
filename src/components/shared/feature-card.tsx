import { FileText, HeartPulse, Mic2, PanelsTopLeft, Sparkles } from "lucide-react";
import { Card } from "@/components/ui/card";

const iconMap = {
  sparkles: Sparkles,
  panels: PanelsTopLeft,
  mic: Mic2,
  heart: HeartPulse,
  file: FileText,
};

export function FeatureCard({ title, description, icon }: { title: string; description: string; icon: keyof typeof iconMap }) {
  const Icon = iconMap[icon];

  return (
    <Card className="transition hover:-translate-y-1 hover:shadow-lg hover:shadow-blue-100">
      <div className="mb-5 inline-flex rounded-2xl bg-primary/10 p-3 text-primary">
        <Icon className="h-6 w-6" />
      </div>
      <h3 className="font-heading text-lg font-extrabold text-foreground">{title}</h3>
      <p className="mt-3 text-sm leading-7 text-muted-foreground">{description}</p>
    </Card>
  );
}
