import { z } from "zod";

const namePattern = /^[\p{L}\p{M}][\p{L}\p{M}\s.'’_-]*$/u;
const emailSchema = z.string().trim().toLowerCase().email("أدخل بريدًا إلكترونيًا صحيحًا.").max(254);
const passwordSchema = z
  .string()
  .min(8, "كلمة المرور يجب ألا تقل عن 8 أحرف.")
  .max(128, "كلمة المرور طويلة جدًا.")
  .refine((value) => /[\p{L}]/u.test(value) && /\d/.test(value), "يجب أن تحتوي كلمة المرور على حرف ورقم على الأقل.");

export const registerRequestSchema = z
  .object({
    fullName: z.string().trim().min(2, "الاسم الكامل مطلوب.").max(100).regex(namePattern, "الاسم يحتوي على رموز غير مسموحة."),
    email: emailSchema,
    password: passwordSchema,
    confirmPassword: z.string().min(1, "تأكيد كلمة المرور مطلوب."),
    role: z.enum(["student_teacher", "faculty_member", "supervisor"], { message: "الدور غير صالح." }),
  })
  .strict()
  .refine((value) => value.password === value.confirmPassword, {
    message: "كلمتا المرور غير متطابقتين.",
    path: ["confirmPassword"],
  });

export const loginRequestSchema = z
  .object({
    email: emailSchema,
    password: z.string().min(1, "كلمة المرور مطلوبة.").max(128),
    rememberMe: z.boolean().optional().default(false),
  })
  .strict();

export const updateProfileRequestSchema = z
  .object({
    fullName: z.string().trim().min(2).max(100).regex(namePattern, "الاسم يحتوي على رموز غير مسموحة.").optional(),
    institution: z.string().trim().max(150).nullable().optional(),
    avatarUrl: z.string().trim().url("رابط الصورة غير صالح.").max(2_048).nullable().optional(),
  })
  .strict()
  .refine((value) => Object.keys(value).length > 0, "يجب إرسال حقل واحد على الأقل.");

export type RegisterInput = z.infer<typeof registerRequestSchema>;
export type LoginInput = z.infer<typeof loginRequestSchema>;
export type UpdateProfileInput = z.infer<typeof updateProfileRequestSchema>;
