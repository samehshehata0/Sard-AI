"use client";

import { Save, X } from "lucide-react";
import Image from "next/image";
import { useState } from "react";
import { authService } from "@/services/auth-service";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card } from "@/components/ui/card";
import type { User } from "@/types/user";

function isPreviewableUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function AvatarSection({ user }: { user: User }) {
  const [value, setValue] = useState(user.avatarUrl ?? "");
  const [saved, setSaved] = useState(user.avatarUrl ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isDirty = value !== saved;

  async function save() {
    setError(null);
    setIsSaving(true);
    try {
      await authService.updateProfile({ avatarUrl: value.trim() || null });
      setSaved(value);
    } catch (err) {
      setError(err instanceof Error ? err.message : "تعذر حفظ الصورة.");
    } finally {
      setIsSaving(false);
    }
  }

  function discard() {
    setValue(saved);
    setError(null);
  }

  return (
    <Card>
      <h3 className="font-heading text-xl font-extrabold text-foreground">الصورة الشخصية</h3>
      <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-3xl bg-gradient-to-l from-primary to-secondary font-heading text-2xl font-black text-primary-foreground">
          {isPreviewableUrl(value) ? (
            <Image unoptimized src={value} alt="" width={80} height={80} className="h-full w-full object-cover" />
          ) : (
            user.fullName.trim().charAt(0)
          )}
        </div>
        <div className="flex-1">
          <label className="block text-xs font-bold text-muted-foreground">رابط الصورة</label>
          <input value={value} onChange={(event) => setValue(event.target.value)} className="input mt-2" placeholder="https://..." />
        </div>
      </div>
      {error ? <p className="mt-3 text-sm font-bold text-destructive" role="alert">{error}</p> : null}
      {isDirty ? (
        <div className="mt-4 flex gap-2">
          <ArabicButton type="button" onClick={save} disabled={isSaving} icon={<Save className="h-4 w-4" />}>
            {isSaving ? "جارٍ الحفظ..." : "حفظ الصورة"}
          </ArabicButton>
          <ArabicButton type="button" variant="ghost" onClick={discard} disabled={isSaving} icon={<X className="h-4 w-4" />}>
            تراجع
          </ArabicButton>
        </div>
      ) : null}
    </Card>
  );
}
