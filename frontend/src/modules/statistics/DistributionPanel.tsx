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
 *
 * ## 모자라도 빈손으로 두지 않는다
 *
 * n < 8 이면 후보 셋이 전부 「표본 모자람」 이다. 그것만 보이면 **막다른 길**이다 —
 * 사람이 할 수 있는 판단이 아무것도 없다. 그래서 **가정 없는 요약**을 늘 위에
 * 둔다: n·최소·중앙·최대와, 관측 최소값이 덮는 분위수.
 *
 * 그 분위수가 이 화면의 답이다. 시편 3개면 최소값이 덮는 것이 63% 분위수라,
 * **하위 5% 근처에도 못 간다.** 그 사실을 수로 보여 주면 「데이터가 모자라다」 가
 * 「지금 데이터로는 여기까지 말할 수 있고, 분포 없이 하위 5% 를 말하려면 59개가
 * 필요하다」 로 바뀐다. 앞엣말은 막다른 길이고 뒤엣말은 판단이다.
 *
 * ## 모달로 띄운다
 *
 * 표·곡선과 같은 자리에 펼치면 **묶음 하나가 화면 두 판을 먹는다** — 인장
 * MD/TD 에 DMA 까지면 셋이고, 아래 묶음을 보려면 이걸 다시 접어야 했다. 여기서
 * 하는 일은 *하나의 항목*을 파고드는 일이라 그동안 다른 것을 볼 이유가 없다.
 */

import { useEffect, useState } from 'react'
import { Sigma } from 'lucide-react'

import { statisticsApi } from '@/modules/statistics/api'
import type { DistributionCandidate, DistributionReport } from '@/modules/statistics/api'
import type { components } from '@/shared/api/schema'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
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

  const unit = report?.si_unit ?? '1'

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Sigma className="size-4" />
        산포 분포 적합
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        {/* 표가 일곱 칸이라 좁으면 가로로 샌다. 세로는 화면을 넘기지 않고 안에서
            굴린다 — 후보가 셋에 관측값 목록까지 붙는다. */}
        <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>산포 분포 적합</DialogTitle>
            <DialogDescription>
              정규·로그정규·와이블을 나란히 맞춥니다. <b>고르지 않고 견줘 줍니다.</b>{' '}
              평균·SD 는 산포가 <i>얼마나</i> 큰지를 말하고, 여기서는 <i>어떤 모양</i>인지를
              묻습니다 — <b>하위 5%</b> 는 같은 평균·같은 SD 에서도 모양에 따라 달라집니다.
            </DialogDescription>
          </DialogHeader>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
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

          {/* **표보다 먼저 온다.** 후보가 전부 「표본 모자람」 일 때 이것이
              화면에 남는 유일한 판단 거리다. */}
          {report.empirical && <EmpiricalSummary summary={report.empirical} unit={unit} />}

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
          </div>
        </DialogContent>
      </Dialog>
    </>
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
/**
 * **분포를 가정하지 않은 요약.** 적합이 하나도 못 돌아도 이것은 있다.
 *
 * 「최소값이 덮는 분위수」 가 핵심이다 — 순서통계량이라 어떤 분포에서도 참이고,
 * 작은 표본에서 **정직하게 약하다.** 그 약함이 곧 답이다.
 */
function EmpiricalSummary({
  summary,
  unit,
}: {
  summary: components['schemas']['EmpiricalOut']
  unit: string
}) {
  const show = (value: number | null) => (value === null ? '—' : formatScalar(value, unit, null))
  const cells: [string, number | null][] = [
    ['n', summary.count],
    ['최소', summary.minimum],
    ['1사분위', summary.q1],
    ['중앙', summary.median],
    ['3사분위', summary.q3],
    ['최대', summary.maximum],
  ]
  return (
    <section className="bg-muted/30 space-y-2 rounded-md border p-3">
      <header className="flex flex-wrap items-baseline gap-2">
        <h5 className="text-sm font-medium">가정 없이 말할 수 있는 것</h5>
        <span className="text-muted-foreground text-xs">
          분포를 안 씁니다 — <b>있는 값 그대로</b>입니다.
        </span>
      </header>

      <dl className="grid grid-cols-3 gap-x-4 gap-y-1 text-xs sm:grid-cols-6">
        {cells.map(([label, value]) => (
          <div key={label}>
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="font-mono">{label === 'n' ? (value ?? 0) : show(value)}</dd>
          </div>
        ))}
      </dl>

      {summary.covered_quantile !== null && summary.minimum !== null && (
        <p className="text-xs">
          {/* **여기가 이 칸의 요점이다.** 「모자랍니다」 는 막다른 길이고, 이
              문장은 지금 데이터로 어디까지 말할 수 있는지를 준다. */}
          관측 최소값 <b className="font-mono">{show(summary.minimum)}</b> 은{' '}
          <b>{(summary.covered_quantile * 100).toFixed(0)}% 분위수</b>의{' '}
          {(summary.confidence * 100).toFixed(0)}% 신뢰 하한입니다 — 시편 {summary.count}개로
          분포 없이 말할 수 있는 데까지입니다.
          {summary.needed_for_design !== null && (
            <>
              {' '}
              하위 5% 를 이렇게 말하려면 <b>{summary.needed_for_design}개</b>가 필요합니다.{' '}
              <b>분포를 맞추는 이유가 그 수입니다</b> — 59개를 재는 대신 모양을 가정해 꼬리를
              외삽하고, 그 가정이 맞는지를 아래 <b>p</b> 가 묻습니다.
            </>
          )}
        </p>
      )}
    </section>
  )
}

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
