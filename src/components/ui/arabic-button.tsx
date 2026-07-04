import Link from "next/link";
import { type ComponentPropsWithoutRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type ButtonProps = ComponentPropsWithoutRef<"button"> & {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "success";
  href?: string;
  icon?: ReactNode;
};

const variants = {
  primary: "bg-gradient-to-l from-primary to-secondary text-primary-foreground shadow-lg shadow-primary/20 hover:shadow-primary/30",
  secondary: "bg-foreground text-background hover:opacity-90",
  outline: "border border-border bg-card text-foreground hover:border-primary/30 hover:bg-primary/10",
  ghost: "text-muted-foreground hover:bg-muted hover:text-foreground",
  success: "bg-success text-background hover:opacity-90",
};

export function ArabicButton({ className, variant = "primary", href, icon, children, ...props }: ButtonProps) {
  const classes = cn(
    "inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl px-5 py-2.5 text-sm font-bold transition focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background disabled:cursor-not-allowed disabled:opacity-60",
    variants[variant],
    className,
  );

  if (href) {
    return (
      <Link href={href} className={classes}>
        {icon}
        {children}
      </Link>
    );
  }

  return (
    <button className={classes} {...props}>
      {icon}
      {children}
    </button>
  );
}
