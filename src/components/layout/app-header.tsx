import Link from "next/link";
import { Bell, Menu, Search } from "lucide-react";
import { ArabicButton } from "@/components/ui/arabic-button";
import { BrandLogo } from "@/components/brand/brand-logo";
import { ThemeToggle } from "@/components/theme/theme-toggle";

export function AppHeader({ title }: { title: string }) {
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-background/90 px-4 py-4 backdrop-blur md:px-8">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
        <div className="flex items-center gap-3 lg:hidden">
          <button className="rounded-2xl border border-border bg-card p-3 text-muted-foreground" aria-label="فتح القائمة">
            <Menu className="h-5 w-5" />
          </button>
          <BrandLogo compact />
        </div>
        <div className="hidden lg:block">
          <h1 className="font-heading text-2xl font-extrabold text-foreground">{title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">مساحة عمل عربية لبناء قصة تعليمية متكاملة</p>
        </div>
        <div className="flex flex-1 items-center justify-end gap-3">
          <div className="hidden max-w-sm flex-1 items-center gap-2 rounded-2xl border border-border bg-card px-4 py-3 md:flex">
            <Search className="h-5 w-5 text-muted-foreground" />
            <input className="w-full bg-transparent text-sm outline-none" placeholder="ابحث عن قصة أو تقرير" />
          </div>
          <ThemeToggle compact />
          <button className="rounded-2xl border border-border bg-card p-3 text-muted-foreground shadow-sm" aria-label="الإشعارات">
            <Bell className="h-5 w-5" />
          </button>
          <ArabicButton href="/stories/new" className="hidden md:inline-flex">
            إنشاء قصة
          </ArabicButton>
        </div>
      </div>
      <nav className="mt-4 flex gap-2 overflow-x-auto pb-1 lg:hidden">
        {[
          ["/dashboard", "لوحة التحكم"],
          ["/stories/new", "إنشاء قصة"],
          ["/history", "السجل"],
          ["/settings", "الإعدادات"],
        ].map(([href, label]) => (
          <Link key={href} href={href} className="shrink-0 rounded-full bg-card px-4 py-2 text-sm font-bold text-muted-foreground shadow-sm">
            {label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
