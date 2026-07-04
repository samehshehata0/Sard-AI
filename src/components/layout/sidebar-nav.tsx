"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, BookOpen, Clock3, Home, Mic2, PanelsTopLeft, Settings, UserRound, Video } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "لوحة التحكم", icon: Home },
  { href: "/stories/new", label: "إنشاء قصة", icon: BookOpen },
  { href: "/stories/demo-story/editor", label: "محرر القصة", icon: BookOpen },
  { href: "/stories/demo-story/storyboard", label: "اللوحات القصصية", icon: PanelsTopLeft },
  { href: "/stories/demo-story/video", label: "الفيديو", icon: Video },
  { href: "/stories/demo-story/audio", label: "التعليق الصوتي", icon: Mic2 },
  { href: "/stories/demo-story/reports", label: "التقارير", icon: BarChart3 },
  { href: "/history", label: "السجل", icon: Clock3 },
  { href: "/profile", label: "الملف الشخصي", icon: UserRound },
  { href: "/settings", label: "الإعدادات", icon: Settings },
];

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <nav className="mt-8 space-y-1">
      {navItems.map((item) => {
        const active = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href));

        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-bold text-muted-foreground transition hover:bg-primary/10 hover:text-primary",
              active && "bg-primary/10 text-primary",
            )}
          >
            <item.icon className="h-5 w-5" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
