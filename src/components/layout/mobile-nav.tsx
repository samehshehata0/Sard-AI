"use client";

import { Menu, Search, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { createPortal } from "react-dom";
import { BrandLogo } from "@/components/brand/brand-logo";
import { SidebarNav } from "@/components/layout/sidebar-nav";

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const [lastPathname, setLastPathname] = useState(pathname);

  if (pathname !== lastPathname) {
    setLastPathname(pathname);
    setOpen(false);
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-2xl border border-border bg-card p-3 text-muted-foreground"
        aria-label="فتح القائمة"
      >
        <Menu className="h-5 w-5" />
      </button>
      {open
        ? createPortal(
            <div className="fixed inset-0 z-30 lg:hidden">
              <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
              <div className="absolute inset-y-0 start-0 w-72 overflow-y-auto bg-card p-5 shadow-xl">
                <div className="flex items-center justify-between">
                  <BrandLogo href="/dashboard" />
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="rounded-2xl border border-border bg-background p-2 text-muted-foreground"
                    aria-label="إغلاق القائمة"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
                <div className="mt-5 flex items-center gap-2 rounded-2xl border border-border bg-background px-4 py-3">
                  <Search className="h-5 w-5 text-muted-foreground" />
                  <input className="w-full bg-transparent text-sm outline-none" placeholder="ابحث عن قصة أو تقرير" />
                </div>
                <SidebarNav />
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
