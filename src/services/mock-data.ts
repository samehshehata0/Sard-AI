import type { Assessment } from "@/types/assessment";
import type { GenerationJob } from "@/types/generation";
import type { Project, ProjectCardView, StoryEditorData, StoryScene } from "@/types/project";
import type { ReportView } from "@/types/report";
import type { User } from "@/types/user";

export const mockUser: User = {
  id: "user-demo",
  fullName: "Sameh",
  email: "sameh@university.edu",
  role: "student_teacher",
  institution: "كلية التربية",
  avatarUrl: null,
  createdAt: "2026-01-10T09:00:00.000Z",
  updatedAt: "2026-06-28T09:00:00.000Z",
};

export const mockProjects: Project[] = [
  {
    id: "demo-story", userId: mockUser.id, title: "رحلة قطرة ماء", educationalTopic: "أهمية الحفاظ على الماء",
    learningObjectives: ["أن يشرح المتعلم معنى ترشيد استهلاك الماء.", "أن يذكر المتعلم ثلاث ممارسات يومية للحفاظ على الماء.", "أن يربط المتعلم بين السلوك الشخصي وحماية البيئة."],
    learnerAge: "9-11 سنة", educationLevel: "المرحلة الابتدائية", learnerCharacteristics: "أمثلة بصرية وحوار قصير",
    storyStyle: "حواري", voiceTone: "مشجعة", requestedOutputs: ["text", "audio", "video"],
    prompt: "قصة تعليمية عربية عن ترشيد الماء", status: "completed", videoUrl: null, audioUrl: null,
    thumbnailUrl: null, errorMessage: null, createdAt: "2026-06-28T09:00:00.000Z", updatedAt: "2026-06-28T10:00:00.000Z",
  },
  {
    id: "plants-story", userId: mockUser.id, title: "سر النبتة الصغيرة", educationalTopic: "احتياجات النبات للنمو",
    learningObjectives: ["أن يحدد المتعلم احتياجات النبات."], learnerAge: "9-11 سنة", educationLevel: "المرحلة الابتدائية",
    learnerCharacteristics: "تعلم بصري", storyStyle: "حواري", voiceTone: "هادئة", requestedOutputs: ["text", "audio", "video"],
    prompt: "حوار بين طفل ونبتة", status: "processing", videoUrl: null, audioUrl: null, thumbnailUrl: null,
    errorMessage: null, createdAt: "2026-06-25T09:00:00.000Z", updatedAt: "2026-06-25T10:00:00.000Z",
  },
  {
    id: "fractions-story", userId: mockUser.id, title: "مخبز الكسور", educationalTopic: "فهم الكسور البسيطة",
    learningObjectives: ["أن يربط المتعلم الكسور بالمشاركة اليومية."], learnerAge: "12-14 سنة", educationLevel: "المرحلة المتوسطة",
    learnerCharacteristics: "أمثلة حياتية", storyStyle: "واقعي", voiceTone: "مشجعة", requestedOutputs: ["text"],
    prompt: "موقف تعليمي في مخبز", status: "draft", videoUrl: null, audioUrl: null, thumbnailUrl: null,
    errorMessage: null, createdAt: "2026-06-21T09:00:00.000Z", updatedAt: "2026-06-21T10:00:00.000Z",
  },
];

export const mockProjectCards: ProjectCardView[] = [
  { id: "demo-story", title: "رحلة قطرة ماء", topic: "أهمية الحفاظ على الماء", status: "مكتملة", date: "28 يونيو 2026", quality: 92, stage: "المرحلة الابتدائية", duration: "4 دقائق", description: "قصة تعليمية عن قطرة ماء تتعلم كيف يحافظ الأطفال على الموارد الطبيعية في المدرسة والمنزل." },
  { id: "plants-story", title: "سر النبتة الصغيرة", topic: "احتياجات النبات للنمو", status: "قيد المعالجة", date: "25 يونيو 2026", quality: 84, stage: "المرحلة الابتدائية", duration: "3 دقائق", description: "حوار لطيف بين طفل ونبتة يوضح أثر الضوء والماء والتربة." },
  { id: "fractions-story", title: "مخبز الكسور", topic: "فهم الكسور البسيطة", status: "مسودة", date: "21 يونيو 2026", quality: 76, stage: "المرحلة المتوسطة", duration: "5 دقائق", description: "موقف حياتي داخل مخبز يساعد المتعلمين على ربط الكسور بالمشاركة اليومية." },
];

export const mockScenes: StoryScene[] = [
  { number: 1, title: "قطرة تبحث عن بيتها", visual: "قطرة ماء صغيرة تتحرك بين الأشجار والأنهار بأسلوب كرتوني هادئ.", narration: "في صباح مشرق، بدأت قطرة ماء صغيرة رحلتها لتتعلم كيف يحافظ الناس على الماء.", prompt: "مشهد كرتوني عربي هادئ، قطرة ماء مبتسمة، أشجار خضراء، نهر صاف، ألوان ناعمة.", status: "تم الإنشاء" },
  { number: 2, title: "الصنبور المفتوح", visual: "طفل يلاحظ صنبورًا مفتوحًا في ساحة المدرسة ويتوقف للتفكير.", narration: "رأت القطرة ماءً ينساب بلا فائدة، فسألت الطفل: هل يمكن أن نجد طريقة أفضل؟", prompt: "ساحة مدرسة عربية، طفل فضولي، صنبور ماء، تعبير تعاطف وتعليم، إضاءة صباحية.", status: "يحتاج مراجعة" },
  { number: 3, title: "وعد الحفاظ", visual: "الأطفال يضعون ملصقات توعوية قرب مصادر الماء في المدرسة.", narration: "اتفق الأطفال على إغلاق الصنابير واستخدام الماء بحكمة، فابتسمت القطرة وعرفت أنها في بيت آمن.", prompt: "طلاب يعلقون ملصقات حفظ الماء، بيئة مدرسية مبهجة، أسلوب رسوم تعليمية.", status: "قيد الانتظار" },
];

export const mockEditorData: StoryEditorData = {
  project: mockProjects[0],
  storyContent: `بدأت القصة في صباح صاف عندما استيقظت قطرة ماء صغيرة فوق ورقة خضراء. كانت القطرة تريد أن تعرف لماذا يطلب المعلم من الطلاب عدم الإسراف في الماء.

سافرت القطرة إلى المدرسة، وهناك رأت طفلًا يغسل يديه ويترك الصنبور مفتوحًا. اقتربت منه بلطف وقالت: كل قطرة لها رحلة طويلة، وعندما نهدر الماء نفقد فرصة أن يستفيد منه إنسان أو نبات.

فكر الطفل قليلًا، ثم أغلق الصنبور ودعا زملاءه لصنع ملصقات صغيرة تذكّر الجميع بالحفاظ على الماء. وفي نهاية اليوم شعرت القطرة أن رسالتها وصلت بطريقة بسيطة ومفرحة.`,
  characters: ["قطرة الماء", "سامي", "المعلمة نورة", "أصدقاء الصف"],
  objectives: mockProjects[0].learningObjectives,
  suggestions: ["أضف سؤالًا تأمليًا في نهاية القصة.", "اجعل الحوار أقصر للمرحلة الابتدائية.", "اربط المشهد الثاني بسلوك داخل المنزل أيضًا."],
};

export const mockGeneration: GenerationJob = {
  id: "generation-demo", projectId: "demo-story", type: "video", provider: "mock-provider",
  providerJobId: null, status: "processing", outputUrl: null, errorMessage: null,
  createdAt: "2026-06-28T10:00:00.000Z", completedAt: null,
};

export const mockAssessment: Assessment = {
  id: "assessment-demo", projectId: "demo-story", userId: mockUser.id,
  stressAnswers: [2, 2, 1], motivationAnswers: [5, 4, 4],
  stressScore: 34, motivationScore: 88, wellBeingScore: 82, createdAt: "2026-06-28T10:00:00.000Z",
};

export const mockReport: ReportView = {
  id: "report-demo", projectId: "demo-story", progressScore: 91, wellBeingScore: 82,
  recommendations: ["استخدم سؤالًا افتتاحيًا يثير الفضول.", "أضف معيار تقييم بسيط للطلاب بعد القصة.", "صدّر التقرير مع نسخة السيناريو للمراجعة الأكاديمية."],
  createdAt: "2026-06-28T10:00:00.000Z", overall: 91,
  scores: [
    { label: "درجة جودة القصة", value: 92, icon: "book" }, { label: "درجة التوافق التعليمي", value: 90, icon: "sparkles" },
    { label: "درجة الاتساق البصري", value: 88, icon: "play" }, { label: "درجة وضوح اللغة", value: 94, icon: "file" },
    { label: "مؤشر الرفاه الأكاديمي", value: 82, icon: "heart" },
  ],
  strengths: ["الأهداف التعليمية واضحة ومناسبة للمرحلة.", "الشخصيات قريبة من بيئة المتعلم.", "اللغة عربية بسيطة وتدعم الفهم."],
  improvements: ["تقليل طول النص الصوتي في المشهد الثاني.", "إضافة نشاط ختامي قصير بعد المشاهدة.", "توحيد وصف الألوان في مطالبات الصور."],
};

export const mockDashboardStats = [
  { label: "عدد القصص", value: "24", hint: "6 قصص هذا الشهر", color: "blue" },
  { label: "القصص المكتملة", value: "18", hint: "نسبة إنجاز 75%", color: "green" },
  { label: "متوسط جودة القصص", value: "89%", hint: "تحسن بمقدار 7%", color: "purple" },
  { label: "مؤشر الرفاه الأكاديمي", value: "82%", hint: "مستقر وإيجابي", color: "teal" },
];

export const mockWellBeing = { index: 82, stress: 34, motivation: 88, note: "مستوى الضغط الأكاديمي منخفض نسبيًا مع دافعية ذاتية مرتفعة. يوصى بتقسيم العمل إلى جلسات قصيرة." };
