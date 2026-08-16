/**
 * 단위 API — 읽기 전용.
 *
 * 쓰기가 없는 것이 의도다. 환산 계수와 저장 단위는 이미 저장된 숫자의 뜻이라
 * 화면에서 고칠 수 없다 — 이유는 `UnitsPage` 머리글에 적혀 있다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type UnitsStatus = components['schemas']['UnitsOut']
export type UnitDimension = components['schemas']['DimensionOut']

export const unitsApi = {
  list: () => api.get<UnitsStatus>('/units'),
}
