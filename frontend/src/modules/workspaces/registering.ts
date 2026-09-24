/** 등록 부서의 기본값 — `RegisteringWorkspaceField` 와 그것을 품은 편집기가 함께 쓴다. */

/** 처음 고를 값 — 내 소속, 없으면 첫 멤버십. 둘 다 없으면 서버가 이유를 말한다. */
export function defaultRegisteringSlug(
  user: { home_workspace_slug?: string | null; memberships?: { slug: string }[] } | null
): string | null {
  return user?.home_workspace_slug ?? user?.memberships?.[0]?.slug ?? null
}
