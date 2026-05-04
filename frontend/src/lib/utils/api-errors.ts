import type { ZodError } from 'zod';

type JsonValue = null | string | number | boolean | JsonValue[] | { [k: string]: JsonValue };

export type ApiErrorBody = {
  error: string;
  code?: string;
  issues?: JsonValue;
} & Record<string, JsonValue>;

function safeJson(value: unknown): JsonValue {
  // Zod issues and most error payloads are plain objects, but their TS types are not assignable to JsonValue.
  // We serialize + parse to guarantee JSON-safe output and to satisfy the JsonValue type.
  try {
    return JSON.parse(JSON.stringify(value)) as JsonValue;
  } catch {
    return String(value);
  }
}

export function toErrorMessage(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value instanceof Error && typeof value.message === 'string' && value.message) return value.message;
  if (value && typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return 'Request failed';
    }
  }
  return 'Request failed';
}

export function zodToApiError(error: ZodError): ApiErrorBody {
  return {
    error: 'Validation failed',
    code: 'VALIDATION_ERROR',
    issues: safeJson(error.issues),
  };
}

