import { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: ComponentPropsWithoutRef<"div">) {
  return <div className={cn("rounded-3xl border border-border bg-card p-6 text-card-foreground shadow-sm shadow-black/5", className)} {...props} />;
}

export function SectionTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="space-y-2">
      <h2 className="font-heading text-2xl font-extrabold text-foreground md:text-3xl">{title}</h2>
      {subtitle ? <p className="max-w-2xl text-sm leading-7 text-muted-foreground md:text-base">{subtitle}</p> : null}
    </div>
  );
}
