import { FileQuestion } from "lucide-react";
import { Card } from "@/components/ui/card";

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <Card className="flex flex-col items-center justify-center py-12 text-center">
      <div className="rounded-3xl bg-muted p-4 text-muted-foreground">
        <FileQuestion className="h-10 w-10" />
      </div>
      <h3 className="mt-4 font-heading text-xl font-extrabold text-foreground">{title}</h3>
      <p className="mt-2 max-w-md text-sm leading-7 text-muted-foreground">{description}</p>
    </Card>
  );
}
