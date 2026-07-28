import { RefreshCw, Save, WandSparkles } from "lucide-react";
import { ArabicButton } from "@/components/ui/arabic-button";
import { Card } from "@/components/ui/card";
import type { StoryEditorData } from "@/types/project";

export function StoryEditor({ data }: { data: StoryEditorData }) {
  const { characters, objectives, storyContent, suggestions } = data;
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
      <div className="space-y-6">
        <Card>
          <label className="block">
            <span className="mb-2 block text-sm font-bold text-muted-foreground">عنوان القصة</span>
            <input className="input text-xl font-extrabold" defaultValue={data.project.title} />
          </label>
          <label className="mt-5 block">
            <span className="mb-2 block text-sm font-bold text-muted-foreground">محتوى القصة</span>
            <textarea className="input min-h-80 leading-8" defaultValue={storyContent} />
          </label>
          <div className="mt-5 flex flex-wrap gap-3">
            <ArabicButton icon={<Save className="h-4 w-4" />}>حفظ التعديلات</ArabicButton>
            <ArabicButton href="/stories/demo-story/storyboard" variant="outline" icon={<WandSparkles className="h-4 w-4" />}>توليد اللوحات القصصية</ArabicButton>
            <ArabicButton variant="ghost" icon={<RefreshCw className="h-4 w-4" />}>إعادة التوليد</ArabicButton>
          </div>
        </Card>
        <div className="grid gap-6 md:grid-cols-2">
          <ListCard title="الشخصيات" items={characters} />
          <ListCard title="الأهداف التعليمية" items={objectives} />
        </div>
      </div>
      <Card className="h-fit bg-gradient-to-br from-card to-primary/10">
        <h3 className="font-heading text-xl font-extrabold text-foreground">اقتراحات الذكاء الاصطناعي</h3>
        <div className="mt-5 space-y-3">
          {suggestions.map((item) => (
            <div key={item} className="rounded-2xl bg-card p-4 text-sm leading-7 text-muted-foreground shadow-sm">
              {item}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function ListCard({ title, items }: { title: string; items: string[] }) {
  return (
    <Card>
      <h3 className="font-heading text-lg font-extrabold text-foreground">{title}</h3>
      <ul className="mt-4 space-y-3">
        {items.map((item) => (
          <li key={item} className="rounded-2xl bg-muted p-3 text-sm font-bold text-muted-foreground">
            {item}
          </li>
        ))}
      </ul>
    </Card>
  );
}
