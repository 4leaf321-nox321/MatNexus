/**
 * 분포 적합 — **흩어짐에 모양을 붙인다.**
 *
 * 위쪽 표가 평균·SD·CV 를 낸다. 그것은 흩어짐이 *얼마나* 큰지를 말하고, 여기서는
 * *어떤 모양*인지를 묻는다. 설계가 실제로 알고 싶은 것은 대개 **하위 5% 가
 * 얼마인가**인데, 그 답은 같은 평균·같은 SD 에서도 모양에 따라 달라진다.
 *
 * ## 고르지 않고 견줘 준다
 *
 * 경화식 화면과 같은 태도다(ADR 0009). 1등만 보이면 2등과 얼마나 갈렸는지가
 * 사라지고, 그 차이가 작을 때는 **데이터가 정한 것이 아니라 우리가 정한 것**이
 * 된다. ΔAICc 가 2 미만이면 서버가 그 사실을 안내로 말한다.
 *
 * ## 실패한 후보도 숨기지 않는다
 *
 * 안 뜨면 "안 해 봤다" 로 읽힌다. 그리고 **"모자라다" 와 "안 맞는다" 를 다른
 * 색으로** 보인다 — 한 칸에 넣으면 *와이블이 안 맞는 재료*와 *시편이 모자란
 * 재료*가 같아 보인다.
 */

import { useEffect, useState } from 'react'

import { statisticsApi } from '@/modules/statistics/api'
import type { DistributionCandidate, DistributionReport } from '@/modules/statistics/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { formatScalar } from '@/shared/units'

/** 상태 → 사람이 읽는 말. **셋을 한 색으로 칠하지 않는다.** */
const STATUS: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' }> = {
  succeeded: { label: '맞춰 봄', variant: 'default' },
  not_eligible: { label: '표본 모자람', variant: 'secondary' },
  failed: { label: '실패', variant: 'outline' },
}

export function DistributionPanel({
  materialId,
  testTypeKey,
  orientation,
}: {
  materialId: string
  testTypeKey: string
  orientation: string
}) {
  const [keys, setKeys] = useState<{ key: string; label: string; count: number }[]>([])
  const [chosen, setChosen] = useState<string | null>(null)
  const [report, setReport] = useState<DistributionReport | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open || keys.length > 0) return
    statisticsApi
      .distributable(materialId, testTypeKey, orientation)
      .then((rows) => setKeys(rows.map((r) => ({ key: r.key, label: r.label, count: r.count }))))
      .catch((caught: unknown) =>
        setError(caught instanceof Error ? caught : new Error('항목을 읽지 못했습니다.'))
      )
  }, [open, keys.length, materialId, testTypeKey, orientation])

  async function run(key: string) {
    setChosen(key)
    setBusy(true)
    setError(null)
    setReport(null)
    try {
      setReport(await statisticsApi.distributions(materialId, testTypeKey, orientation, key))
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('분포를 맞추지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        흩어짐의 모양 보기
      </Button>
    )
  }

  const unit = report?.si_unit ?? '1'

  return (
    <section className="space-y-3 rounded-md border p-3">
      <header className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-medium">흩어짐의 모양</h4>
        <span className="text-muted-foreground text-xs">
          정규·로그정규·와이블을 나란히 맞춥니다. <b>고르지 않고 견줘 줍니다.</b>
        </span>
      </header>

      <ErrorNotice error={error} />

      <div className="flex flex-wrap gap-1.5">
        {keys.map((item) => (
          <Button
            key={item.key}
            size="sm"
            variant={chosen === item.key ? 'default' : 'outline'}
            onClick={() => void run(item.key)}
            disabled={busy}
          >
            {item.label}
            {/* **눌러 보고 나서 "모자랍니다" 를 받는 것보다 미리 아는 것이 낫다.** */}
            <span className="ml-1 opacity-60">n={item.count}</span>
          </Button>
        ))}
        {keys.length === 0 && !error && (
          <span className="text-muted-foreground text-xs">항목을 읽는 중…</span>
        )}
      </div>

      {busy && (
        <p className="text-muted-foreground text-xs">
          부트스트랩 999회를 도는 중입니다 — 파라미터를 데이터에서 추정했으므로 표준 임계값표를 쓸
          수 없습니다.
        </p>
      )}

      {report && (
        <>
          {report.notes.length > 0 && (
            <ul className="text-muted-foreground space-y-1 text-xs">
              {report.notes.map((note) => (
                <li key={note} className="border-l-2 pl-2">
                  {note}
                </li>
              ))}
            </ul>
          )}

          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>분포</TableHead>
                  <TableHead>파라미터</TableHead>
                  <TableHead className="text-right">ΔAICc</TableHead>
                  <TableHead className="text-right">p</TableHead>
                  <TableHead className="text-right">하위 5%</TableHead>
                  <TableHead className="text-right">중앙</TableHead>
                  <TableHead className="text-right">상위 5%</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.candidates.map((item) => (
                  <CandidateRow
                    key={item.key}
                    item={item}
                    unit={unit}
                    best={item.key === report.best}
                  />
                ))}
              </TableBody>
            </Table>
          </div>

          <p className="text-muted-foreground text-xs">
            <b>ΔAICc</b> 는 1등과의 차이입니다 — 2 미만이면 이 데이터로는 구별되지 않습니다.{' '}
            <b>p</b> 는 <i>이 분포가 맞기는 하나</i>를 묻습니다(작으면 아니라는 뜻이고, 큰 p 가
            맞다는 증명은 아닙니다). 둘이 다른 것을 보므로 함께 읽으세요.
          </p>

          <Observations report={report} />
        </>
      )}
    </section>
  )
}

function CandidateRow({
  item,
  unit,
  best,
}: {
  item: DistributionCandidate
  unit: string
  best: boolean
}) {
  const status = STATUS[item.status] ?? { label: item.status, variant: 'outline' as const }
  const quantile = (name: string) => {
    const value = item.quantiles[name]
    return value === undefined ? '—' : formatScalar(value, unit, null)
  }
  // **p 가 작으면 짚는다.** 표에서 눈에 안 띄면 안 보는 것과 같다.
  const rejected = item.p_value !== null && item.p_value < 0.05

  return (
    <TableRow className={best ? 'bg-muted/40' : undefined}>
      <TableCell>
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-medium">{item.label}</span>
          {best && <Badge className="text-[10px]">1등</Badge>}
          {item.status !== 'succeeded' && (
            <Badge variant={status.variant} className="text-[10px]">
              {status.label}
            </Badge>
          )}
        </div>
        {item.reason && <p className="text-muted-foreground mt-0.5 text-xs">{item.reason}</p>}
      </TableCell>
      <TableCell className="font-mono text-xs">
        {item.parameters.length === 0
          ? '—'
          : item.parameters
              .map(
                (value, index) =>
                  `${item.parameter_labels[index] ?? item.parameter_names[index]} ${Number(
                    value.toPrecision(4)
                  )}`
              )
              .join(' · ')}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {item.delta_aicc === null ? '—' : item.delta_aicc.toFixed(2)}
      </TableCell>
      <TableCell
        className={`text-right tabular-nums ${rejected ? 'text-destructive font-medium' : ''}`}
      >
        {item.p_value === null ? '—' : item.p_value.toFixed(3)}
      </TableCell>
      <TableCell className="text-right tabular-nums">{quantile('p05')}</TableCell>
      <TableCell className="text-right tabular-nums">{quantile('p50')}</TableCell>
      <TableCell className="text-right tabular-nums">{quantile('p95')}</TableCell>
    </TableRow>
  )
}

/**
 * 쓰지 못한 값. **조용히 빼면 "왜 8개죠" 를 답할 수 없다.**
 *
 * 전부 정상이면 안 그린다 — 빈 표는 화면만 먹는다.
 */
function Observations({ report }: { report: DistributionReport }) {
  const problems = report.observations.filter((item) => item.status !== 'observed')
  if (problems.length === 0) return null
  const words: Record<string, string> = {
    missing: '그 시편에 이 항목이 없음',
    non_finite: '값이 유한하지 않음',
    censored: '정의역 밖(양수만 받는 분포)',
  }
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium">쓰지 못한 값 {problems.length}개</p>
      <ul className="text-muted-foreground space-y-0.5 text-xs">
        {problems.map((item) => (
          <li key={`${item.specimen_label}-${item.status}`}>
            {item.specimen_label} — {words[item.status] ?? item.status}
          </li>
        ))}
      </ul>
    </div>
  )
}
