import { StoryStatus } from "@/lib/constants/types";

export const stories = [
  {
    id: "demo-story",
    title: "رحلة قطرة ماء",
    topic: "أهمية الحفاظ على الماء",
    status: "مكتملة" as StoryStatus,
    date: "28 يونيو 2026",
    quality: 92,
    stage: "المرحلة الابتدائية",
    duration: "4 دقائق",
    description: "قصة تعليمية عن قطرة ماء تتعلم كيف يحافظ الأطفال على الموارد الطبيعية في المدرسة والمنزل.",
  },
  {
    id: "plants-story",
    title: "سر النبتة الصغيرة",
    topic: "احتياجات النبات للنمو",
    status: "قيد المعالجة" as StoryStatus,
    date: "25 يونيو 2026",
    quality: 84,
    stage: "المرحلة الابتدائية",
    duration: "3 دقائق",
    description: "حوار لطيف بين طفل ونبتة يوضح أثر الضوء والماء والتربة.",
  },
  {
    id: "fractions-story",
    title: "مخبز الكسور",
    topic: "فهم الكسور البسيطة",
    status: "مسودة" as StoryStatus,
    date: "21 يونيو 2026",
    quality: 76,
    stage: "المرحلة المتوسطة",
    duration: "5 دقائق",
    description: "موقف حياتي داخل مخبز يساعد المتعلمين على ربط الكسور بالمشاركة اليومية.",
  },
] as const;
