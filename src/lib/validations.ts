import { z } from "zod";

export const loginSchema = z.object({
  email: z.string().min(1, "البريد الإلكتروني مطلوب").email("أدخل بريدًا إلكترونيًا صحيحًا"),
  password: z.string().min(8, "كلمة المرور يجب ألا تقل عن 8 أحرف"),
  remember: z.boolean().optional(),
});

export const registerSchema = z
  .object({
    fullName: z.string().min(2, "الاسم الكامل مطلوب"),
    email: z.string().min(1, "البريد الإلكتروني مطلوب").email("أدخل بريدًا إلكترونيًا صحيحًا"),
    password: z.string().min(8, "كلمة المرور يجب ألا تقل عن 8 أحرف"),
    confirmPassword: z.string().min(1, "تأكيد كلمة المرور مطلوب"),
    role: z.string().min(1, "اختر الدور"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "كلمتا المرور غير متطابقتين",
    path: ["confirmPassword"],
  });

export const storyWizardSchema = z.object({
  title: z.string().min(1, "عنوان القصة مطلوب"),
  topic: z.string().min(1, "الموضوع التعليمي مطلوب"),
  stage: z.string().min(1, "المرحلة التعليمية مطلوبة"),
  duration: z.string().min(1, "مدة القصة مطلوبة"),
  objectives: z.array(z.string().min(1, "لا تترك الهدف فارغًا")).min(1, "يجب إضافة هدف تعليمي واحد على الأقل"),
  age: z.string().min(1, "العمر مطلوب"),
  level: z.string().min(1, "المستوى مطلوب"),
  needs: z.string().min(1, "الاحتياجات التعليمية مطلوبة"),
  style: z.string().min(1, "اختر أسلوب القصة"),
  tone: z.string().min(1, "اختر نبرة الصوت"),
  output: z.string().min(1, "اختر نوع المخرجات"),
});
