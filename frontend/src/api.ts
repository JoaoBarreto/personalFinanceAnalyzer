export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
}

let csrf = "";
export const setCsrf = (t: string) => {
  csrf = t;
};

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (method !== "GET") headers["X-CSRF-Token"] = csrf;
  const res = await fetch(path, { method, headers, body: payload, credentials: "same-origin" });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && path !== "/api/auth/login") window.dispatchEvent(new Event("unauthenticated"));
    throw new ApiError(res.status, data?.detail ?? res.statusText);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, params?: Record<string, string | number | boolean | undefined | null>) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
    const qs = q.toString();
    return request<T>("GET", qs ? `${path}?${qs}` : path);
  },
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  del: <T = void>(path: string) => request<T>("DELETE", path),
};

/** Mensagem legível a partir de um erro da API (inclui o detalhe de reconciliação). */
export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail as { mensagem?: string; diferenca?: string } | string;
    if (typeof d === "object" && d && "mensagem" in d) return `${d.mensagem} (diferença ${d.diferenca} €)`;
    if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg).join("; ");
    return typeof d === "string" ? d : e.message;
  }
  return e instanceof Error ? e.message : String(e);
}

export type Me = { id: number; username: string; nome: string; csrf_token: string };
export type Category = { id: number; nome: string; parent_id: number | null; tipo: string; cor: string | null; ativa: boolean; n_movimentos?: number };
export type Account = { id: number; nome: string; banco: string; parser_id: string; moeda: string; titular_id: number | null; arquivada: boolean };
export type User = { id: number; username: string; nome: string };
export type Tx = {
  id: number; conta_id: number; data_movimento: string; descricao_original: string; descricao_normalizada: string;
  montante: string; saldo_apos: string | null; categoria_id: number | null; categoria_nome: string | null;
  categoria_origem: string | null; notas: string | null; atualizado_por: number | null;
};

export type Coverage = {
  conta_id: number; nome: string; primeiro: string | null; ultimo: string | null; n_movimentos: number;
  falhas: { de: string; ate: string; diferenca: string }[]; ok: boolean;
};
