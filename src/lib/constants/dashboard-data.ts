export const dashboardStats = [
  { label: "عدد القصص", value: "24", hint: "6 قصص هذا الشهر", color: "blue" },
  { label: "القصص المكتملة", value: "18", hint: "نسبة إنجاز 75%", color: "green" },
  { label: "متوسط جودة القصص", value: "89%", hint: "تحسن بمقدار 7%", color: "purple" },
  { label: "مؤشر الرفاه الأكاديمي", value: "82%", hint: "مستقر وإيجابي", color: "teal" },
] as const;

export const wellBeing = {
  index: 82,
  stress: 34,
  motivation: 88,
  note: "مستوى الضغط الأكاديمي منخفض نسبيًا مع دافعية ذاتية مرتفعة. يوصى بتقسيم العمل إلى جلسات قصيرة.",
};
