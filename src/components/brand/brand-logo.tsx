import Image from "next/image";
import Link from "next/link";
import { cn } from "@/lib/utils";

export function BrandLogo({ compact, className, href = "/" }: { compact?: boolean; className?: string; href?: string }) {
  const textVisibility = compact === true ? "hidden" : compact === false ? undefined : "hidden lg:block";
  return (
    <Link href={href} className={cn("inline-flex items-center gap-3", className)} aria-label="سَرْد AI">
      <Image src="/sard-logo-no-text.svg" alt="" aria-hidden="true" width={44} height={44} className="shrink-0" />
      <span className={cn("leading-none", textVisibility)}>
        <span className="block font-heading text-2xl font-black text-foreground">سَرْد AI</span>
        <span className="mt-1 block text-xs font-semibold text-muted-foreground">من الفكرة... إلى قصة تعليمية متكاملة</span>
      </span>
    </Link>
  );
}
