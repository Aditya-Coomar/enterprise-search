export type Doc = {
  id: string;
  name: string;
  size: number;
  created: number;
  status: string;
  total: number;
  pages: number[];
  visualCount: number;
  visualStatus: string;
  error: string;
  warning: string;
  sample: boolean;
};
export type Hit = {
  page: number;
  heading: string;
  snippet: string;
  signals: string[];
};
export type Mode = "hybrid" | "text" | "visual";
export const url = (id: string) => "/workspace-api/documents/" + id;
export const size = (n: number) =>
  n >= 1e6
    ? (n / 1e6).toFixed(1) + " MB"
    : Math.max(1, Math.round(n / 1000)) + " KB";
export async function request<T>(
  address: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const response = await fetch(address, {
    method,
    cache: "no-store",
    headers: {
      "X-Folio-Request": "1",
      ...(data ? { "Content-Type": "application/json" } : {}),
    },
    body: data ? JSON.stringify(data) : undefined,
  });
  if (!response.ok) {
    const info = await response.json().catch(() => ({}));
    throw new Error(info.error || "The workspace is unavailable. Try again.");
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export const message = (e: unknown) =>
  e instanceof Error ? e.message : "Something went wrong. Please try again.";
export function status(d: Doc) {
  return d.status === "ready"
    ? "Searchable"
    : d.status === "error"
      ? "Needs attention"
      : d.status === "queued"
        ? "Queued"
        : "Indexing";
}
