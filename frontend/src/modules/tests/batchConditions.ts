/**
 * 일괄 등록의 시험 조건 — **종류 기본값 + 줄마다 다른 값.**
 *
 * 전에는 조건이 시험 종류마다 한 벌이라, 한 배치에 온도가 다른 파일(23 °C · 80 °C)을 섞으면
 * 전부 같은 조건으로 올라갔다 — 오류 없이(2026-09-29 지적). 이제 줄이 제 값을 가진다.
 * 비운 칸은 종류 기본값을 따른다.
 *
 * 순수 함수로 둔 이유: 화면(`BatchUploadPage`)은 파일·재료·시편을 흉내 내야 시험할 수 있어
 * 무겁다. 「어느 값이 실리나」 는 여기서 잠근다.
 */

import type { TestType } from '@/modules/tests/api'

/** 문자열 조건(폼 상태) — 조건 키 → 입력 문자열. */
export type ConditionDraft = Record<string, string>

/**
 * 한 줄이 서버로 보낼 조건.
 *
 * - 줄에 적은 값이 종류 기본값을 이긴다. 줄에서 비운 칸은 기본값을 따른다.
 * - **그 종류가 선언한 칸만** 싣는다 — 종류를 바꾼 줄에 옛 종류의 칸이 남아 실리지 않게.
 * - 숫자 칸은 숫자로 바꾼다. 빈 칸은 보내지 않는다.
 */
export function rowConditions(
  typeKey: string,
  defaults: Record<string, ConditionDraft>,
  overrides: ConditionDraft,
  types: TestType[]
): Record<string, unknown> {
  const definition = types.find((type) => type.key === typeKey)
  if (!definition) return {}
  const merged: ConditionDraft = { ...(defaults[typeKey] ?? {}) }
  for (const [key, value] of Object.entries(overrides)) {
    if (value !== '') merged[key] = value
  }
  const out: Record<string, unknown> = {}
  for (const field of definition.conditions) {
    const value = merged[field.key]
    if (value === undefined || value === '') continue
    out[field.key] = field.value_type === 'number' ? Number(value) : value
  }
  return out
}

/** 줄에서 기본값과 다르게 적은 칸의 수 — 표의 「개별 N」. */
export function overrideCount(overrides: ConditionDraft): number {
  return Object.values(overrides).filter((value) => value !== '').length
}
