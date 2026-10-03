/**
 * 합성 곡선 미리보기 — **덱의 「곡선 합성」 이 지을 곡선을 미리 본다** (2026-10-03).
 *
 * 문헌에는 곡선이 없다. 덱은 스칼라(E · 항복 · 인장 · 연신율)로 σ-ε 곡선을 지어 소성 표로
 * 싣는데, 전에는 덱 파일을 열어 숫자를 읽기 전에는 어떤 곡선인지 볼 길이 없었다.
 *
 * ## 실측처럼 보이면 해가 된다
 *
 * 제목부터 「합성 — 실측이 아니다」 다. 모델과 그 근사가 무엇을 과대 · 과소평가하는지
 * (`note`)를 곡선 위에 적고, 어느 값으로 지었는지 출처를 함께 단다.
 *
 * ## 누를 때 짓는다
 *
 * 상세를 열 때마다 짓지 않는다 — 대부분은 값 표를 보러 온다. 같은 계산이 서버의 덱 경로에
 * 있으므로(`litdeck.synthetic_preview`) 여기서 다시 짓지 않는다.
 */

import { LineChart } from 'lucide-react'
import { useState } from 'react'

import { catalogApi } from '@/modules/catalog/api'
import type { SyntheticCurvePreview } from '@/modules/catalog/api'
import { CurveChart } from '@/modules/tests/CurveChart'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { axisLabel, formatValue, toDisplay } from '@/shared/units'

export function SyntheticCurveSection({ materialId }: { materialId: string }) {
  const [preview, setPreview] = useState<SyntheticCurvePreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState<Error | null>(null)

  async function load() {
    setLoading(true)
    setFailed(null)
    try {
      setPreview(await catalogApi.syntheticCurve(materialId))
    } catch (caught) {
      setFailed(caught instanceof Error ? caught : new Error('곡선을 짓지 못했습니다.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="space-y-2" aria-label="합성 곡선 미리보기">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">합성 곡선 — 실측이 아니다</h2>
        {!preview && (
          <Button size="sm" variant="outline" disabled={loading} onClick={() => void load()}>
            <LineChart className="size-4" />
            {loading ? '짓는 중…' : '미리보기'}
          </Button>
        )}
      </div>
      {!preview && (
        <p className="text-muted-foreground text-sm">
          문헌 덱에서 「곡선 합성」 을 켜면 이 재료의 스칼라로 소성 곡선을 지어 싣습니다. 어떤
          곡선이 될지 여기서 먼저 봅니다.
        </p>
      )}
      <ErrorNotice error={failed} />

      {preview && !preview.ok && (
        <p className="rounded-md border px-3 py-2 text-sm" role="status">
          {preview.why}
        </p>
      )}

      {preview?.ok && (
        <div className="space-y-2 rounded-md border p-3">
          <p className="text-sm" role="status">
            <b>{preview.model}</b> — {preview.note}
            {preview.table_points === 0 && ' 덱에 실릴 소성 표는 없습니다.'}
          </p>
          <CurveChart
            points={(preview.strain ?? []).map((strain, at) => [
              strain,
              toDisplay(preview.stress?.[at] ?? 0, 'Pa'),
            ])}
            xLabel={axisLabel('공칭 변형률', '1', 'strain')}
            yLabel={axisLabel('공칭 응력', 'Pa')}
            height={240}
          />
          <ul className="space-y-0.5 text-sm">
            {preview.youngs_modulus != null && (
              <li>탄성계수 {formatValue(preview.youngs_modulus, null, 'Pa')} — 탄성 블록에 선 값</li>
            )}
            {(preview.inputs ?? []).map((one) => (
              <li key={one.item}>
                {one.item}{' '}
                {formatValue(
                  one.value_si,
                  null,
                  one.si_unit ?? null,
                  one.si_unit === '1' ? 'strain' : undefined
                )}{' '}
                — {one.reference}
              </li>
            ))}
            {(preview.notes ?? []).map((note) => (
              <li key={note} className="text-amber-700 dark:text-amber-500">
                {note}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
