import { Card } from "@/components/ui/card";

const colorMap: Record<string, string> = {
  blue: "from-primary to-primary",
  green: "from-success to-accent",
  purple: "from-secondary to-secondary",
  teal: "from-accent to-primary",
};

export function StatCard({ label, value, hint, color }: { label: string; value: string; hint: string; color: string }) {
  return (
    <Card className="overflow-hidden p-0">
      <div className={`h-2 bg-gradient-to-l ${colorMap[color] ?? colorMap.blue}`} />
      <div className="p-5">
        <p className="text-sm font-bold text-muted-foreground">{label}</p>
        <p className="mt-3 font-numbers text-3xl font-bold text-foreground">{value}</p>
        <p className="mt-2 text-sm text-muted-foreground">{hint}</p>
      </div>
    </Card>
  );
}
