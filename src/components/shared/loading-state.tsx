export function LoadingState() {
  return (
    <div className="grid gap-4 md:grid-cols-3" aria-label="جار التحميل">
      {[1, 2, 3].map((item) => (
        <div key={item} className="h-36 animate-pulse rounded-3xl bg-muted" />
      ))}
    </div>
  );
}
