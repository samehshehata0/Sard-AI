export interface ApiSuccess<T> {
  data: T;
  meta?: PaginationMeta;
}

export interface PaginationMeta {
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
}

export interface PaginationParams {
  page?: number;
  pageSize?: number;
}

export interface ApiFieldError {
  field: string;
  message: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: ApiFieldError[];
    requestId?: string;
  };
}

export type AsyncState<T> =
  | { status: "idle"; data: null; error: null }
  | { status: "loading"; data: T | null; error: null }
  | { status: "success"; data: T; error: null }
  | { status: "error"; data: T | null; error: Error };
