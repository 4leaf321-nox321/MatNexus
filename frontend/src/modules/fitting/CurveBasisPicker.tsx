/**
 * 대표 곡선 고르기 — 평균 · 중앙값 · 하한 · 상한(2026-09-29).
 *
 * 상·하한은 **방법까지 골라야** 선다. 표준편차 배수를 미리 켜 두지 않는 이유: 기본값이 곧
 * 결정이 되는데, 아무도 그것을 결정이라고 여기지 않는다(늘리기·섞기 비중과 같은 판단).
 */

import { BASIS_KINDS, boundOptions, optionKey } from '@/modules/fitting/curveBasis'
import type { CurveBasis } from '@/modules/fitting/curveBasis'
import { Button } from '@/shared/components/ui/button'

export function CurveBasisPicker({
  value,
  onChange,
  samples,
}: {
  value: CurveBasis
  onChange: (next: CurveBasis) => void
  /** 쓸 시편 수 — 상·하한은 2개부터, 공차 한계는 3개부터다. */
  samples: number
}) {
  const kind = value.kind ?? 'mean'
  const bounded = kind === 'lower' || kind === 'upper'
  const picked = optionKey(value)
  const options = bounded ? boundOptions(kind) : []
  const active = options.find((one) => one.key === picked)

  return (
    <div className="space-y-2">
      <div role="group" aria-label="대표 곡선" className="flex flex-wrap items-center gap-1.5">
        {BASIS_KINDS.map((one) => {
          const needsSpread = one.kind === 'lower' || one.kind === 'upper'
          const blocked = needsSpread && samples < 2
          return (
            <Button
              key={one.kind}
              type="button"
              size="sm"
              variant={kind === one.kind ? 'default' : 'outline'}
              aria-pressed={kind === one.kind}
              disabled={blocked}
              title={blocked ? '시편이 1개라 흩어짐을 모릅니다 — 상·하한을 낼 수 없습니다' : one.hint}
              // **방향만 바꾸면 방법은 둔다** — 하한 -2σ 에서 상한을 누르면 +2σ 가 된다.
              onClick={() =>
                onChange(needsSpread && bounded ? { ...value, kind: one.kind } : { kind: one.kind })
              }
            >
              {one.label}
            </Button>
          )
        })}
        <span className="text-muted-foreground text-xs">
          곡선(소성 표·식)에만 적용합니다 — 탄성계수·밀도는 그대로입니다.
        </span>
      </div>

      {bounded && (
        <div
          role="group"
          aria-label={`${kind === 'lower' ? '하한' : '상한'}을 내는 방법`}
          className="flex flex-wrap items-center gap-1.5"
        >
          {options.map((one) => {
            const blocked = samples < one.minSamples
            return (
              <Button
                key={one.key}
                type="button"
                size="sm"
                variant={picked === one.key ? 'secondary' : 'ghost'}
                aria-pressed={picked === one.key}
                disabled={blocked}
                title={blocked ? `시편 ${one.minSamples}개부터 냅니다 (지금 ${samples}개)` : one.hint}
                onClick={() =>
                  onChange({
                    kind,
                    method: one.method,
                    ...(one.method === 'sd' ? { k: one.k } : {}),
                  })
                }
              >
                {one.label}
              </Button>
            )
          })}
        </div>
      )}
      {bounded && (
        <p className="text-muted-foreground text-xs">
          {active ? active.hint : '방법을 고르면 맞춰 볼 수 있습니다.'}
        </p>
      )}
    </div>
  )
}
