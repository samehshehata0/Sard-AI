import { Card } from "@/components/ui/card";

export function DashboardCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <h3 className="font-heading text-xl font-extrabold text-foreground">{title}</h3>
      <div className="mt-4">{children}</div>
    </Card>
  );
}
