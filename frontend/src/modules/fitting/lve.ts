/**
 * 선형탄성구간(LVE) 판정 — **컴포넌트 파일에 두지 않는다.** 컴포넌트와 함수를 한
 * 파일에서 내보내면 fast refresh 가 그 파일 전체를 다시 그린다.
 */

import type { components } from '@/shared/api/schema'

type StatisticsGroup = components['schemas']['GroupOut']

/** 이 묶음으로 LVE 카드를 만들 수 있나 — 선형 한계 변형률을 낸 채택 결과가 있는가. */
export function hasLve(group: Pick<StatisticsGroup, 'scalars'>): boolean {
  return group.scalars.some((one) => one.key === 'lve_strain_limit')
}
