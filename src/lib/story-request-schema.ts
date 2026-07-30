import { z } from "zod";
import { storyWizardSchema } from "@/lib/validations";

export const storyGenerationSchema = storyWizardSchema.extend({
  speakerGender: z.enum(["male", "female"], { message: "اختر جنس الراوي" }),
});
