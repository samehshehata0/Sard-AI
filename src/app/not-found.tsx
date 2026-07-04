import { BrandLogo } from "@/components/brand/brand-logo";
import { ArabicButton } from "@/components/ui/arabic-button";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-lg text-center">
        <div className="flex justify-center"><BrandLogo compact /></div>
        <p className="mt-8 font-numbers text-7xl font-bold text-primary">404</p>
        <h1 className="mt-4 font-heading text-3xl font-black text-foreground">الصفحة غير موجودة</h1>
        <p className="mt-3 leading-8 text-muted-foreground">قد يكون الرابط غير صحيح أو تم نقل الصفحة إلى مكان آخر داخل المنصة.</p>
        <ArabicButton href="/dashboard" className="mt-7">العودة إلى لوحة التحكم</ArabicButton>
      </div>
    </main>
  );
}
