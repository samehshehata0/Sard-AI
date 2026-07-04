import Link from "next/link";
import { cn } from "@/lib/utils";

export function BrandLogo({ compact = false, className }: { compact?: boolean; className?: string }) {
  return (
    <Link href="/" className={cn("inline-flex items-center gap-3", className)} aria-label="سَرْد AI">
      <svg width="44" height="44" viewBox="0 0 44 44" role="img" aria-hidden="true" className="shrink-0">
        <rect width="44" height="44" rx="16" fill="url(#logoGradient)" />
        <path d="M11 17.5c4.1-2.2 7.4-2 10 0v13c-2.6-1.8-5.9-2-10 0v-13Z" fill="var(--primary-foreground)" opacity=".92" />
        <path d="M33 17.5c-4.1-2.2-7.4-2-10 0v13c2.6-1.8 5.9-2 10 0v-13Z" fill="color-mix(in srgb, var(--primary-foreground) 86%, var(--primary))" />
        <path d="M26.5 21.2v5.6l4.5-2.8-4.5-2.8Z" fill="var(--primary)" />
        <path d="M22 9l1.1 2.8L26 13l-2.9 1.1L22 17l-1.1-2.9L18 13l2.9-1.2L22 9Z" fill="var(--warning)" />
        <defs>
          <linearGradient id="logoGradient" x1="40" y1="4" x2="4" y2="40">
            <stop stopColor="var(--primary)" />
            <stop offset="1" stopColor="var(--secondary)" />
          </linearGradient>
        </defs>
      </svg>
      {!compact ? (
        <span className="leading-none">
          <span className="block font-heading text-2xl font-black text-foreground">سَرْد AI</span>
          <span className="mt-1 block text-xs font-semibold text-muted-foreground">من الفكرة... إلى قصة تعليمية متكاملة</span>
        </span>
      ) : null}
    </Link>
  );
}
