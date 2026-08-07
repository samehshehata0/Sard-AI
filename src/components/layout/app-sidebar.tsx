import { BrandLogo } from "@/components/brand/brand-logo";
import { SidebarNav } from "@/components/layout/sidebar-nav";
import { cn } from "@/lib/utils";
import { LogoutButton } from "@/components/auth/logout-button";

export function AppSidebar({ className }: { className?: string }) {
  return (
    <aside className={cn("sticky top-0 hidden h-screen w-72 shrink-0 border-l border-border bg-card/95 p-5 shadow-sm lg:block", className)}>
      <BrandLogo />
      <SidebarNav />
      <LogoutButton />
      <div className="mt-8 rounded-3xl bg-gradient-to-l from-accent to-primary p-5 text-primary-foreground">
        <p className="font-heading text-lg font-extrabold">مؤشر الرفاه الأكاديمي</p>
        <p className="mt-2 text-sm leading-6 text-primary-foreground/85">جلسات قصيرة، نتائج أفضل، وضغط أقل أثناء بناء القصة.</p>
      </div>
    </aside>
  );
}
