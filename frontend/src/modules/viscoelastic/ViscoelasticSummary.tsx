/**
 * 점탄성 산출물 요약 — **「결과」 탭에서도 보인다.**
 *
 * 사람이 배우는 문법은 하나여야 한다. 값 쪽은 「만들고 → 대표를 고르고(채택) →
 * 재료가 가져간다」 인데, 점탄성만 다른 탭에서 만들어져 「결과」 를 거치지 않는다.
 * 그래서 **점탄성을 통째로 건너뛴 채** 재료 화면에서 물성이 비었다고 여기는 일이
 * 생긴다.
 *
 * 만드는 자리는 안 옮긴다 — 겹치기는 온도 단추와 곡선이 붙어 있어 크고, 여기로
 * 밀어 넣으면 둘 다 좁아진다. **보이는 자리만** 모은다.
 *
 * 그래서 이 상자는 세 가지만 말한다.
 *
 *     무엇이 있나        마스터커브 몇 벌, 그중 대표는 어느 것
 *     어디로 가나        재료의 글로벌 피팅
 *     없으면 무엇을 하나  점탄성 탭으로 가는 길
 */

import { viscoelasticApi } from '@/modules/viscoelastic/api'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { useResource } from '@/shared/hooks/useResource'
import { formatScalar } from '@/shared/units'

export function ViscoelasticSummary({
  testRunId,
  fitCount,
  onGo,
}: {
  testRunId: string
  /** 이 시험의 마스터커브에 맞춘 계수가 몇 벌인가. 시험 상세가 이미 안다. */
  fitCount: number
  onGo: () => void
}) {
  const curves = useResource(() => viscoelasticApi.masterCurves(testRunId), [testRunId])
  const rows = curves.data ?? []
  const primary = rows.find((one) => one.is_primary)

  return (
    <section className="mt-6" aria-label="점탄성 산출물">
      <h2 className="mb-1 font-medium">점탄성</h2>
      <p className="text-muted-foreground mb-2 text-sm">
        온도를 가로질러 겹친 것은 위의 처리 결과가 아니라 <b>마스터커브</b>로 남고,
        재료의 <b>글로벌 피팅</b>과 이 시험의 Prony 적합이 그것을 읽습니다. 만드는 자리는{' '}
        <b>점탄성</b> 탭입니다.
      </p>

      <ErrorNotice error={curves.error} className="mb-2" />

      {rows.length === 0 ? (
        // **건너뛴 것이 여기서 드러나야 한다.** 이 문장이 없으면 「결과」 탭이
        // 빈 것을 보고 이 시험은 할 일이 없다고 여긴다.
        <div className="text-muted-foreground rounded-md border p-4 text-sm">
          아직 마스터커브가 없습니다. 만들면 재료의 <b>글로벌 피팅</b> 후보에 이 시험이
          들어갑니다.
          <div className="mt-2">
            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={onGo}>
              점탄성 탭에서 만들기
            </Button>
          </div>
        </div>
      ) : (
        <div className="rounded-md border p-3 text-sm">
          <div className="space-y-1">
            {rows.map((one) => (
              <div key={one.id} className="flex flex-wrap items-center gap-2 text-xs">
                {one.is_primary ? (
                  <Badge variant="secondary" className="text-[10px]">
                    대표
                  </Badge>
                ) : (
                  <span className="w-8" />
                )}
                <span className="font-mono">
                  {formatScalar(one.reference_temperature_k, 'K', 'temperature')} 기준
                </span>
                <span className="text-muted-foreground">{one.method}</span>
                <span className="text-muted-foreground">
                  {one.minimum_frequency_hz.toExponential(1)} ~{' '}
                  {one.maximum_frequency_hz.toExponential(1)} Hz
                </span>
              </div>
            ))}
          </div>
          <p className="text-muted-foreground mt-2 text-xs">
            {/* **대표가 무엇을 정하는지 적는다.** 「채택」 과 같은 자리라는 것이
                보여야 두 갈래가 한 문법으로 읽힌다. */}
            재료의 글로벌 피팅은 <b>대표</b> 하나를 읽습니다
            {primary
              ? ` — 지금은 ${formatScalar(primary.reference_temperature_k, 'K', 'temperature')} 기준입니다.`
              : '.'}{' '}
            맞춘 계수 {fitCount}벌.
          </p>
          <div className="mt-2">
            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={onGo}>
              점탄성 탭으로
            </Button>
          </div>
        </div>
      )}
    </section>
  )
}
