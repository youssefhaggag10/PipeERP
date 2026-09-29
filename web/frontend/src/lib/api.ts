export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
  }
}

function cookie(name: string): string | undefined {
  const prefix = `${name}=`;
  return document.cookie
    .split(";")
    .map((value) => value.trim())
    .find((value) => value.startsWith(prefix))
    ?.slice(prefix.length);
}

async function errorPayload(
  response: Response,
): Promise<{ message: string; code?: string }> {
  try {
    const payload = (await response.json()) as {
      detail?: string | { code?: string; message?: string };
    };
    if (typeof payload.detail === "object" && payload.detail)
      return {
        message: payload.detail.message ?? "تعذر تنفيذ العملية",
        code: payload.detail.code,
      };
    return { message: payload.detail ?? "تعذر تنفيذ العملية" };
  } catch {
    return { message: "تعذر الاتصال بالخادم" };
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = cookie("pipeerp_csrf");
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (
    response.status === 401 &&
    retry &&
    !["/auth/login", "/auth/refresh"].includes(path)
  ) {
    try {
      await api("/auth/refresh", { method: "POST" }, false);
      return api<T>(path, options, false);
    } catch {
      throw new ApiError("انتهت الجلسة؛ سجّل الدخول مرة أخرى", 401);
    }
  }
  if (!response.ok) {
    const error = await errorPayload(response);
    throw new ApiError(error.message, response.status, error.code);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
