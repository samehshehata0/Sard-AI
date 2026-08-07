import { HeartPulse } from "lucide-react";
import { Card } from "@/components/ui/card";
import { mockWellBeing } from "@/services/mock-data";

export function WellBeingIndexCard() {
  const wellBeing = mockWellBeing;
  return (
    <Card className="bg-gradient-to-br from-card to-accent/10">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-heading text-xl font-extrabold text-foreground">مؤشر الرفاه الأكاديمي</p>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">{wellBeing.note}</p>
        </div>
        <div className="rounded-2xl bg-accent/15 p-3 text-accent">
          <HeartPulse className="h-6 w-6" />
        </div>
      </div>
      <div className="mt-6 h-3 rounded-full bg-muted">
        <div className="h-3 rounded-full bg-gradient-to-l from-accent to-primary" style={{ width: `${wellBeing.index}%` }} />
      </div>
      <div className="mt-5 grid grid-cols-3 gap-3 text-center">
        <div className="rounded-2xl bg-card p-3">
          <p className="font-numbers text-2xl font-bold text-foreground">{wellBeing.index}%</p>
          <p className="text-xs font-bold text-muted-foreground">المؤشر</p>
        </div>
        <div className="rounded-2xl bg-card p-3">
          <p className="font-numbers text-2xl font-bold text-warning">{wellBeing.stress}%</p>
          <p className="text-xs font-bold text-muted-foreground">الضغط الأكاديمي</p>
        </div>
        <div className="rounded-2xl bg-card p-3">
          <p className="font-numbers text-2xl font-bold text-success">{wellBeing.motivation}%</p>
          <p className="text-xs font-bold text-muted-foreground">الدافعية الذاتية</p>
        </div>
      </div>
    </Card>
  );
}
