import type { ResearchPageProps } from "./types";

export type ResearchPageLoadResult =
  | { status: "ready"; data: ResearchPageProps }
  | { status: "deterministic-only"; message: string };

export async function getResearchResource<T>(
  resource: string,
  fetcher: typeof fetch = fetch,
): Promise<T> {
  const response = await fetcher(`/api/research/${resource}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Research API request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export async function loadResearchPage(
  fetcher: typeof fetch = fetch,
): Promise<ResearchPageLoadResult> {
  try {
    const data = await getResearchResource<ResearchPageProps>("comparisons", fetcher);
    return { status: "ready", data };
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown research API error";
    return { status: "deterministic-only", message };
  }
}
