/**
 * 카드의 **대표 곡선을 무엇으로** 만들까 — 평균 · 중앙값 · 하한 · 상한(2026-09-29).
 *
 * 카드 만들기가 늘 평균이었다. 해석은 강도 평가에 하한, 충돌 에너지·성형 하중에 상한 곡선을
 * 한 번 더 돌린다. 계산은 서버가 한다(`matcore.statistics.pick_curve`) — 여기는 고르는 말과
 * 「고를 준비가 됐나」 만 안다.
 */

import type { components } from '@/shared/api/schema'

export type CurveBasis = components['schemas']['CurveBasisIn']
export type BasisKind = CurveBasis['kind']

export const BASIS_KINDS: { kind: NonNullable<BasisKind>; label: string; hint: string }[] = [
  { kind: 'mean', label: '평균', hint: '점마다 시편들의 평균' },
  { kind: 'median', label: '중앙값', hint: '점마다 가운데 값 — 이상치 하나에 덜 끌려갑니다' },
  { kind: 'lower', label: '하한', hint: '강도 평가처럼 보수적으로 볼 때' },
  { kind: 'upper', label: '상한', hint: '충돌 에너지·성형 하중처럼 크게 볼 때' },
]

export interface BoundOption {
  key: string
  method: NonNullable<CurveBasis['method']>
  k?: number
  label: string
  hint: string
  /** 이 방법이 서려면 필요한 시편 수. */
  minSamples: number
}

/** 상·하한을 내는 방법. 표준편차 배수는 **고를 수만 있다** — 기본값이 곧 결정이 되지 않게. */
export function boundOptions(kind: 'lower' | 'upper'): BoundOption[] {
  const lower = kind === 'lower'
  const sign = lower ? '-' : '+'
  const sigma = [1, 2, 3].map((k) => ({
    key: `sd-${k}`,
    method: 'sd' as const,
    k,
    label: `평균 ${sign} ${k}σ`,
    hint: `점마다 평균 ${sign} ${k}×표준편차`,
    minSamples: 2,
  }))
  return [
    ...sigma,
    {
      key: 'tolerance',
      method: 'tolerance',
      label: '공차 한계 (B 기준)',
      hint: '모집단의 90% 를 95% 신뢰로 덮는 선 — 시편이 적을수록 넓습니다',
      minSamples: 3,
    },
    {
      key: 'envelope',
      method: 'envelope',
      label: lower ? '포락선 (점마다 최솟값)' : '포락선 (점마다 최댓값)',
      hint: '잰 것 가운데 가장 끝 — 서로 다른 시편의 점이 섞입니다',
      minSamples: 2,
    },
    {
      key: 'specimen',
      method: 'specimen',
      label: lower ? '가장 낮은 시편' : '가장 높은 시편',
      hint: '시편 하나의 곡선 그대로 — 한 시편의 모양을 지킵니다',
      minSamples: 2,
    },
  ]
}

/** 고른 방법의 키 — 단추가 켜졌는지 가른다. */
export function optionKey(basis: CurveBasis): string | null {
  if (!basis.method) return null
  return basis.method === 'sd' ? `sd-${basis.k}` : basis.method
}

/** 서버에 물을 준비가 됐나 — 상·하한은 방법(과 표준편차면 배수)까지 있어야 한다. */
export function basisReady(basis: CurveBasis): boolean {
  if (basis.kind !== 'lower' && basis.kind !== 'upper') return true
  if (!basis.method) return false
  return basis.method !== 'sd' || typeof basis.k === 'number'
}

/**
 * 요청에 실을 값. **평균이면 안 싣는다** — 서버 기본이 평균이고, 그래야 전과 같은 카드는 전과
 * 같은 근거를 든다(`source.curve_basis` 가 안 생긴다).
 */
export function basisRequest(basis: CurveBasis): CurveBasis | null {
  if (!basis.kind || basis.kind === 'mean' || !basisReady(basis)) return null
  if (basis.kind === 'median') return { kind: 'median' }
  return {
    kind: basis.kind,
    method: basis.method,
    ...(basis.method === 'sd' ? { k: basis.k } : {}),
  }
}

/** 카드 이름 뒤에 붙일 말 — 「인장 MD · 하한 -2σ」. 평균이면 붙이지 않는다. */
export function basisSuffix(basis: CurveBasis): string {
  if (!basis.kind || basis.kind === 'mean' || !basisReady(basis)) return ''
  if (basis.kind === 'median') return ' · 중앙값'
  const side = basis.kind === 'lower' ? '하한' : '상한'
  switch (basis.method) {
    case 'sd':
      return ` · ${side} ${basis.kind === 'lower' ? '-' : '+'}${basis.k}σ`
    case 'tolerance':
      return ` · ${side} 공차한계`
    case 'envelope':
      return ` · ${side} 포락선`
    case 'specimen':
      return ` · ${side} ${basis.kind === 'lower' ? '최저' : '최고'} 시편`
    default:
      return ''
  }
}
