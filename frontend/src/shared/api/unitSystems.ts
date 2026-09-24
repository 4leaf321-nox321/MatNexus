/**
 * 단위계 — **나가는 숫자는 고른 계 하나로 나간다**(ADR 0036).
 *
 * 계를 고르는 자리가 카드 덱만이 아니다. 재료·문헌 내보내기와 문헌 덱도 해석 연동으로
 * 나가는 파일이라 같은 목록에서 고른다. 그 화면들이 카드 모듈을 부르면 도메인끼리
 * 엉키므로 목록은 여기 둔다 — 서버도 계를 정하는 자리를 `app/shared/unit_systems`
 * 하나로 모았다. 이 파일은 아무 도메인 모듈도 import 하지 않는다(`system.ts` 와 같은 자리).
 *
 * ## 기본은 서버가 말한다
 *
 * 화면이 `'si'` 를 적어 두면 서버 기본이 바뀌는 날 **고른 계와 받은 계가 갈린다.**
 * 부품표 덱이 「SI 면 비워 보낸다」 였는데, 비운 것은 이제 mm·N·tonne 이다(2026-09-24).
 * 그래서 기본은 목록의 `is_default` 로 고르고, 요청에는 고른 키를 그대로 적는다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type UnitSystem = components['schemas']['UnitSystemOut']

export const unitSystemsApi = {
  /** 붙박이와 부서가 만든 계. 주소는 카드 모듈의 것이다 — 계를 만들고 지우는 곳이 거기다. */
  list: () => api.get<UnitSystem[]>('/fitting/unit-systems'),
}

/** 사람이 고른 것, 안 골랐으면 서버가 기본이라 한 것. 목록을 아직 못 받았으면 없다. */
export function chosenSystem(systems: UnitSystem[], chosen: string | null): UnitSystem | null {
  return (
    systems.find((one) => one.key === chosen) ??
    systems.find((one) => one.is_default) ??
    systems[0] ??
    null
  )
}
