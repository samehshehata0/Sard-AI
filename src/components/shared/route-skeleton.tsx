import { Card } from "@/components/ui/card";

export function RouteSkeleton() {
  return (
    <div className="space-y-5" aria-label="جار التحميل">
      <div className="h-10 w-64 animate-pulse rounded-2xl bg-muted" />
      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
        {[1, 2, 3, 4].map((item) => (
          <div key={item} className="h-32 animate-pulse rounded-3xl bg-muted" />
        ))}
      </div>
      <div className="h-80 animate-pulse rounded-3xl bg-muted" />
    </div>
  );
}

export function FormSkeleton() {
  return (
    <Card className="space-y-5">
      <div className="h-10 w-56 animate-pulse rounded-2xl bg-muted" />
      <div className="grid gap-4 md:grid-cols-2">
        {[1, 2, 3, 4].map((item) => (
          <div key={item} className="h-14 animate-pulse rounded-2xl bg-muted" />
        ))}
      </div>
      <div className="h-12 w-36 animate-pulse rounded-2xl bg-muted" />
    </Card>
  );
}

export function MediaSkeleton() {
  return (
    <Card>
      <div className="aspect-video animate-pulse rounded-3xl bg-muted" />
      <div className="mt-5 flex gap-3">
        <div className="h-11 w-32 animate-pulse rounded-2xl bg-muted" />
        <div className="h-11 w-32 animate-pulse rounded-2xl bg-muted" />
      </div>
    </Card>
  );
}
