"use client";

import { Laptop, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import { cn } from "@/lib/utils";

const themes = [
  { value: "light", label: "فاتح", icon: Sun },
  { value: "dark", label: "داكن", icon: Moon },
  { value: "system", label: "النظام", icon: Laptop },
] as const;

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  const currentTheme = themes.some((item) => item.value === theme) ? theme : "system";

  if (!mounted) {
    return <div className={cn("h-11 rounded-2xl bg-muted", compact ? "w-11" : "w-44")} aria-hidden="true" />;
  }

  if (compact) {
    const currentIndex = themes.findIndex((item) => item.value === currentTheme);
    const currentItem = themes[currentIndex];
    const nextTheme = themes[(currentIndex + 1 + themes.length) % themes.length];
    const Icon = currentItem.icon;

    return (
      <button
        type="button"
        onClick={() => setTheme(nextTheme.value)}
        className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-border bg-card text-muted-foreground shadow-sm transition hover:bg-muted hover:text-foreground"
        aria-label="تغيير المظهر"
        title={`تغيير المظهر إلى ${nextTheme.label}`}
      >
        <Icon className="h-5 w-5" />
      </button>
    );
  }

  return (
    <div className="inline-flex rounded-2xl border border-border bg-card p-1 shadow-sm" aria-label="اختيار المظهر">
      {themes.map((item) => {
        const Icon = item.icon;
        const active = currentTheme === item.value;
        return (
          <button
            key={item.value}
            type="button"
            onClick={() => setTheme(item.value)}
            className={cn(
              "inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-bold text-muted-foreground transition",
              active && "bg-primary text-primary-foreground shadow-sm",
            )}
          >
            <Icon className="h-4 w-4" />
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
