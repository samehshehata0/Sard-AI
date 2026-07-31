import { z } from "zod";
import { AppError } from "@/server/errors/app-error";

export const objectIdSchema = z.string().regex(/^[a-f\d]{24}$/i, "معرّف المورد غير صالح.");
export const paginationSchema = z.object({
  page: z.coerce.number().int().min(1).default(1),
  pageSize: z.coerce.number().int().min(1).max(100).default(20),
});
export const trimmedString = (max: number) => z.string().trim().min(1).max(max);

export async function parseJsonBody<T>(request: Request, schema: z.ZodType<T>, maxBytes = 100_000): Promise<T> {
  const declaredLength = Number(request.headers.get("content-length") ?? 0);
  if (Number.isFinite(declaredLength) && declaredLength > maxBytes) throw AppError.payloadTooLarge();

  const raw = await request.text();
  if (new TextEncoder().encode(raw).byteLength > maxBytes) throw AppError.payloadTooLarge();

  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw AppError.validation(undefined, "يجب إرسال محتوى JSON صالح.");
  }
  return schema.parse(value);
}
