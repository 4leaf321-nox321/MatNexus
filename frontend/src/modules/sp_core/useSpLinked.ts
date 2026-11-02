/**
 * 대상 키 → 이어진 SP. 기준정보는 값 id, 물성 · 물성군 · 분야는 키.
 *
 * 화면은 줄마다 묻지 않는다 — 한 대상 종류(기준정보는 한 축)를 한 번 받아 키로 찾는다.
 *
 * **못 받아도 화면은 그대로 선다.** 배지는 덧붙이는 것이라, 이것 때문에 목록 위에 오류를
 * 띄우면 정작 보려던 목록이 가려진다. 대상이 없으면(`null`) 묻지 않는다.
 */

import { useMemo } from 'react'

import { spCoreApi } from '@/modules/sp_core/api'
import type { SpLinked, SpTarget } from '@/modules/sp_core/api'
import { useResource } from '@/shared/hooks/useResource'

export function useSpLinked(target: SpTarget | null, vocabulary?: string) {
  const page = useResource(
    () => (target ? spCoreApi.linked(target, vocabulary) : Promise.resolve(null)),
    [target, vocabulary]
  )
  const byRef = useMemo(() => {
    const out = new Map<string, SpLinked[]>()
    for (const one of page.data?.items ?? []) {
      out.set(one.target_ref, [...(out.get(one.target_ref) ?? []), one])
    }
    return out
  }, [page.data])
  return { byRef, truncated: page.data?.truncated ?? false }
}
