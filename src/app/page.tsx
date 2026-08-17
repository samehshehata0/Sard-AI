import { ArrowLeft, PlayCircle, Sparkles } from "lucide-react";
import { BrandLogo } from "@/components/brand/brand-logo";
import { FeatureCard } from "@/components/shared/feature-card";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card, SectionTitle } from "@/components/ui/card";
import { features } from "@/lib/constants/landing-data";

export default function Home() {
  return (
    <main className="min-h-screen overflow-hidden bg-background">
      <header className="mx-auto flex max-w-7xl items-center justify-between px-4 py-5 md:px-8">
        <BrandLogo compact={false} />
        <div className="flex items-center gap-3">
          <ArabicButton href="/login" variant="ghost">تسجيل الدخول</ArabicButton>
          <ArabicButton href="/register" className="hidden sm:inline-flex">إنشاء حساب</ArabicButton>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl items-center gap-10 px-4 pb-16 pt-8 md:px-8 lg:grid-cols-[1.05fr_.95fr] lg:pb-24">
        <div>
          <div className="mb-6 inline-flex items-center gap-2 rounded-full bg-card px-4 py-2 text-sm font-bold text-primary shadow-sm">
            <Sparkles className="h-4 w-4" />
            منصة عربية أولًا للقصص التعليمية الرقمية
          </div>
          <h1 className="font-heading text-4xl font-black leading-tight text-foreground md:text-6xl">سَرْد AI</h1>
          <p className="mt-5 max-w-2xl text-xl font-bold leading-9 text-foreground/80">من الفكرة... إلى قصة تعليمية متكاملة</p>
          <p className="mt-4 max-w-2xl text-lg leading-9 text-muted-foreground">
            تساعد المنصة الطالب المعلم على توليد سيناريو عربي، بناء لوحات قصصية، تجهيز صوت وفيديو، والحصول على تقرير جودة تربوي واضح.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ArabicButton href="/stories/new" icon={<ArrowLeft className="h-4 w-4 rtl-icon" />}>ابدأ إنشاء قصتك</ArabicButton>
            <ArabicButton href="#how" variant="outline" icon={<PlayCircle className="h-4 w-4" />}>شاهد كيف يعمل</ArabicButton>
          </div>
        </div>
        <div className="relative">
          <div className="rounded-[2rem] bg-gradient-to-br from-primary via-secondary to-accent p-1 shadow-2xl shadow-primary/20">
            <Card className="rounded-[1.8rem] p-6">
              <div className="rounded-3xl bg-foreground p-6 text-background">
                <p className="text-sm text-primary">قصة قيد الإنشاء</p>
                <h2 className="mt-3 font-heading text-3xl font-black">رحلة قطرة ماء</h2>
                <p className="mt-4 leading-8 text-background/75">في صباح مشرق، بدأت قطرة ماء صغيرة رحلتها لتتعلم كيف يحافظ الناس على الماء.</p>
              </div>
              <div className="mt-5 grid gap-3 sm:grid-cols-3">
                {["سيناريو", "صوت", "تقرير"].map((item, index) => (
                  <div key={item} className="rounded-2xl bg-muted p-4">
                    <p className="font-numbers text-2xl font-bold text-primary">{index === 0 ? "92%" : index === 1 ? "جاهز" : "91%"}</p>
                    <p className="mt-1 text-sm font-bold text-muted-foreground">{item}</p>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-14 md:px-8">
        <SectionTitle title="ما الذي تقدمه المنصة؟" subtitle="أدوات مركزة تساعدك على الانتقال من فكرة تعليمية قصيرة إلى قصة قابلة للمراجعة والتصدير." />
        <div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-5">
          {features.map((feature) => <FeatureCard key={feature.title} {...feature} />)}
        </div>
      </section>

      <section id="how" className="mx-auto max-w-7xl px-4 py-14 md:px-8">
        <SectionTitle title="كيف يعمل؟" />
        <div className="mt-8 grid gap-5 md:grid-cols-4">
          {["أدخل موضوعك", "راجع السيناريو", "أنشئ الصوت والفيديو", "صدّر القصة والتقرير"].map((item, index) => (
            <Card key={item}>
              <p className="font-numbers text-4xl font-bold text-primary">0{index + 1}</p>
              <h3 className="mt-4 font-heading text-xl font-extrabold text-foreground">{item}</h3>
            </Card>
          ))}
        </div>
      </section>

      <section className="px-4 py-16 md:px-8">
        <div className="mx-auto max-w-5xl rounded-[2rem] bg-gradient-to-l from-accent to-primary p-8 text-center text-primary-foreground md:p-12">
          <h2 className="font-heading text-3xl font-black md:text-4xl">ابدأ قصة تعليمية عربية اليوم</h2>
          <p className="mx-auto mt-4 max-w-2xl leading-8 text-primary-foreground/85">حوّل موضوع الدرس إلى تجربة رقمية جذابة للمتعلمين مع واجهة هادئة وواضحة.</p>
          <ArabicButton href="/stories/new" variant="secondary" className="mt-7 bg-card text-primary hover:bg-muted">ابدأ إنشاء قصتك</ArabicButton>
        </div>
      </section>
    </main>
  );
}
