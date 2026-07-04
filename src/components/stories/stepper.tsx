export function Stepper({ steps, current }: { steps: string[]; current: number }) {
  return (
    <div className="grid gap-3 md:grid-cols-5">
      {steps.map((label, index) => (
        <div key={label} className={`rounded-2xl px-3 py-3 text-sm font-bold ${index <= current ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}>
          {index + 1}. {label}
        </div>
      ))}
    </div>
  );
}
