import { RouteSkeleton } from "@/components/shared/route-skeleton";

export default function Loading() {
  return (
    <main className="min-h-screen bg-background px-4 py-8 md:px-8">
      <div className="mx-auto max-w-7xl">
        <RouteSkeleton />
      </div>
    </main>
  );
}
