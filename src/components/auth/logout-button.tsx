'use client';

import { LogOut } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { authService } from '@/services/auth-service';
import { cn } from '@/lib/utils';

export function LogoutButton({ compact = false }: { compact?: boolean }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function logout() {
    setLoading(true);
    try {
      await authService.logout();
    } finally {
      router.replace('/login');
      router.refresh();
      setLoading(false);
    }
  }

  return (
    <button
      type="button"
      onClick={logout}
      disabled={loading}
      className={cn(
        'flex items-center gap-3 rounded-2xl text-sm font-bold text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive disabled:opacity-60',
        compact
          ? 'h-11 w-11 justify-center border border-border bg-card shadow-sm'
          : 'mt-1 w-full px-4 py-3',
      )}
      aria-label="تسجيل الخروج"
      title="تسجيل الخروج"
    >
      <LogOut className="h-5 w-5" />
      {compact ? null : loading ? 'جارٍ تسجيل الخروج...' : 'تسجيل الخروج'}
    </button>
  );
}
