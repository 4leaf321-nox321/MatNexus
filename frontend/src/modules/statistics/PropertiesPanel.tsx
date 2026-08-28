/**
 * 재료 물성 — **여러 시편이 같은 것을 말하는가.**
 *
 * 시편 하나의 물성은 그 시편의 물성이다. "이 재료의 항복강도" 라고 말하려면 여러
 * 번 재고 그 흩어짐을 봐야 한다. 이 화면이 그 흩어짐을 보여 준다.
 *
 * ## 묶음은 시험종류 + 방향이다
 *
 * 인장은 압연 방향에 따라 물성이 다르다. MD 5개와 TD 5개를 한 통계로 묶으면 CV 가
 * 15% 로 나오는데, **그것은 산포가 아니라 다른 것을 섞은 것이다.**
 *
 * ## 아무것도 조용히 빠지지 않는다
 *
 * 채택 안 된 시험이 몇 건인지, 이상치 후보가 무엇인지, 곡선을 왜 못 냈는지 —
 * 전부 이유와 함께 적는다. n 이 왜 그 수인지 모르면 그 평균은 근거가 없다.
 *
 * ## 평균과 중앙값을 나란히
 *
 * 표준편차는 이상치 하나에 크게 휘둘린다. 둘이 많이 다르다는 것 자체가 신호다.
 */

import { useState } from 'react'
import { AlertTriangle, Save, Sigma } from 'lucide-react'

import { DistributionPanel } from '@/modules/statistics/DistributionPanel'
import { statisticsApi } from '@/modules/statistics/api'
import type { ScalarStats, StatisticsGroup } from '@/modules/statistics/api'
import { CurveChart } from '@/modules/tests/CurveChart'
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
import { useResource } from '@/shared/hooks/useResource'
import { axisLabel, formatScalar, toDisplay } from '@/shared/units'

/** 이 이상이면 흩어짐이 크다고 눈에 띄게 한다. **버리거나 고치지는 않는다.** */
const NOTABLE_CV = 0.05

interface Props {
  materialId: string
}

export function PropertiesPanel({ materialId }: Props) {
  const stats = useResource(() => statisticsApi.forMaterial(materialId), [materialId])
  const [error, setError] = useState<Error | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const groups = stats.data?.groups ?? []

  async function save(group: StatisticsGroup) {
    setError(null)
    try {
      await statisticsApi.save({
        material_id: materialId,
        test_type_key: group.test_type_key,
        orientation: group.orientation,
      })
      setSaved(`${group.test_type_label} · ${group.orientation}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('남기지 못했습니다.'))
    }
  }

  return (
    <section>
      <ErrorNotice error={stats.error ?? error} className="mb-4" />

      {saved && (
        <div className="mb-4 rounded-md border border-emerald-500/40 bg-emerald-500/5 p-3 text-sm">
          <b>{saved}</b> 통계를 남겼습니다. 지금 표본으로 낸 값이 그대로 박혀 있어, 시험이 더 붙어도
          그 값은 바뀌지 않습니다.
        </div>
      )}

      {!stats.loading && groups.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          <Sigma className="mx-auto mb-2 size-5 opacity-50" />
          아직 시험이 없습니다.
        </div>
      )}

      <div className="space-y-6">
        {groups.map((group) => (
          <GroupCard
            key={`${group.test_type_key}-${group.orientation}`}
            materialId={materialId}
            group={group}
            onSave={() => save(group)}
          />
        ))}
      </div>
    </section>
  )
}

function GroupCard({
  group,
  materialId,
  onSave,
}: {
  group: StatisticsGroup
  materialId: string
  onSave: () => void
}) {
  const enough = group.sample_count >= 2
  return (
    <div className="rounded-md border">
      <header className="flex flex-wrap items-center gap-2 border-b p-3">
        <h3 className="font-medium">{group.test_type_label}</h3>
        {/* **방향을 섞지 않는다.** 압연 방향에 따라 물성이 다르다. */}
        <Badge variant="secondary">{group.orientation}</Badge>
        <span className="text-muted-foreground text-sm">채택 {group.sample_count}건</span>
        {group.skipped_unadopted > 0 && (
          <Badge variant="outline" className="text-xs">
            미채택 {group.skipped_unadopted}
          </Badge>
        )}
        {enough && (
          <Button size="sm" variant="outline" className="ml-auto" onClick={onSave}>
            <Save className="size-3.5" />이 통계 남기기
          </Button>
        )}
      </header>

      <div className="space-y-4 p-3">
        {group.notes.length > 0 && (
          <ul className="text-muted-foreground space-y-1 text-xs">
            {group.notes.map((note) => (
              <li key={note} className="border-l-2 pl-2">
                {note}
              </li>
            ))}
          </ul>
        )}

        {group.scalars.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>항목</TableHead>
                <TableHead className="text-right">n</TableHead>
                <TableHead className="text-right">평균</TableHead>
                <TableHead className="text-right">중앙값</TableHead>
                <TableHead className="text-right">표준편차</TableHead>
                <TableHead className="text-right">CV</TableHead>
                <TableHead className="text-right">95% 신뢰구간</TableHead>
                <TableHead>이상치</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {group.scalars.map((row) => (
                <ScalarRow key={row.key} row={row} />
              ))}
            </TableBody>
          </Table>
        )}

        {group.curve && <EnsembleCurve group={group} />}

        {/* **흩어짐이 얼마나 큰지와 어떤 모양인지는 다른 물음이다.** 위 표가
            앞엣것을 냈다. 설계가 묻는 하위 5% 는 모양이 정한다 — 같은 평균과
            같은 SD 에서도 달라진다.

            기본으로 접어 둔다. 부트스트랩 999회가 도는 일이라 물어보지도 않았는데
            돌릴 일이 아니다. */}
        {group.sample_count > 0 && (
          <DistributionPanel
            materialId={materialId}
            testTypeKey={group.test_type_key}
            orientation={group.orientation}
          />
        )}
      </div>
    </div>
  )
}

function ScalarRow({ row }: { row: ScalarStats }) {
  const value = (input: number | null) =>
    input === null ? '—' : formatScalar(input, row.si_unit, row.dimension)
  const notableCv =
    row.coefficient_of_variation !== null && row.coefficient_of_variation >= NOTABLE_CV
  // **평균과 중앙값이 많이 다르면 그 자체가 신호다.** 표준편차는 이상치 하나에
  // 크게 휘둘리므로 둘을 나란히 둔다.
  return (
    <TableRow>
      <TableCell>
        <span className="text-sm">{row.label}</span>
        <p className="text-muted-foreground font-mono text-xs">{row.key}</p>
      </TableCell>
      <TableCell className="text-right tabular-nums">{row.count}</TableCell>
      <TableCell className="text-right tabular-nums">{value(row.mean)}</TableCell>
      <TableCell className="text-muted-foreground text-right tabular-nums">
        {value(row.median)}
      </TableCell>
      <TableCell className="text-right tabular-nums">{value(row.sample_sd)}</TableCell>
      <TableCell className="text-right tabular-nums">
        {row.coefficient_of_variation === null ? (
          '—'
        ) : (
          <span className={notableCv ? 'font-medium text-amber-700 dark:text-amber-500' : ''}>
            {(row.coefficient_of_variation * 100).toPrecision(3)}%
          </span>
        )}
      </TableCell>
      <TableCell className="text-muted-foreground text-right tabular-nums text-xs">
        {row.ci95_low === null ? '—' : `${value(row.ci95_low)} ~ ${value(row.ci95_high)}`}
      </TableCell>
      <TableCell>
        {row.outliers.length === 0 ? (
          <span className="text-muted-foreground text-xs">—</span>
        ) : (
          <div className="space-y-0.5">
            {row.outliers.map((item) => (
              <div key={item.test_run_id} className="text-xs">
                <Badge variant="outline" className="gap-1 text-amber-700 dark:text-amber-500">
                  <AlertTriangle className="size-3" />
                  {item.record_name.split('__').at(-1) ?? item.record_name}
                </Badge>
                {/* **버리지 않았다.** 재료 특성인지 시험 실수인지는 사람이 안다. */}
                <p className="text-muted-foreground mt-0.5">{item.reason}</p>
              </div>
            ))}
          </div>
        )}
      </TableCell>
    </TableRow>
  )
}

function EnsembleCurve({ group }: { group: StatisticsGroup }) {
  // **훅이 조건 뒤에 오면 안 된다.** 곡선이 없는 렌더에서만 훅 하나가 빠져
  // 호출 순서가 달라지고, React 는 그 상태를 다른 훅의 것으로 읽는다.
  const [mode, setMode] = useState<'mean' | 'median'>('mean')
  const curve = group.curve
  if (!curve) return null

  // 표시 단위로 맞춘다. 축만 바꾸고 점을 안 바꾸면 1000배 어긋난다.
  //
  // **단위는 서버가 준다.** 전에는 채널 이름 앞글자로 짐작했다 —
  // `stress*` 면 Pa, 나머지는 전부 무차원. 그래서 변위·온도가 있는 묶음에서
  // m 와 K 가 그대로 나왔고, 축에는 단위가 아예 안 붙었다.
  //
  // 차원은 이름으로 남긴다 — 변형률과 tan δ 는 저장 단위가 둘 다 `1` 이라
  // 단위만으로는 못 가른다(`shared/units.ts` 의 `BY_DIMENSION`).
  const unitOf = (name: string) => curve.units?.[name] ?? '1'
  const dimensionOf = (name: string) => (name.startsWith('strain') ? 'strain' : null)
  const shown = (points: [number, number][]): [number, number][] =>
    points.map(([x, y]) => [
      toDisplay(x, unitOf(curve.x), dimensionOf(curve.x)),
      toDisplay(y, unitOf(curve.y), dimensionOf(curve.y)),
    ])

  const points = shown((mode === 'mean' ? curve.mean : curve.median) as [number, number][])
  /**
   * 대표를 만든 **시편별 원곡선**. 뒤에 흐리게 깔린다.
   *
   * 평균선 하나로는 「열 개가 겹쳐 있다」와 「하나가 딴 데로 가서 평균이
   * 끌려갔다」가 똑같이 생겼다 — 그 둘을 가르는 것이 이 그림의 목적이다.
   */
  const raw = (curve.members ?? []).map((member) => ({
    label: member.record_name,
    points: shown(member.points as [number, number][]),
  }))
  // **1개면 평균도 중앙값도 그 곡선이다.** 고를 것이 없는데 버튼을 두면 눌러
  // 보고 아무것도 안 변하는 것을 확인하게 된다 — 그건 고장으로 읽힌다.
  const single = group.sample_count === 1

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{single ? '곡선' : '대표 곡선'}</span>
        {/* **둘 다 낸다.** 이상치가 있을 때 중앙값이 낫고, 어느 것을 쓸지는
            피팅할 때 고르면 된다. */}
        {!single &&
          (['mean', 'median'] as const).map((option) => (
            <Button
              key={option}
              size="sm"
              variant={mode === option ? 'default' : 'outline'}
              className="h-7 text-xs"
              onClick={() => setMode(option)}
            >
              {option === 'mean' ? '평균' : '중앙값'}
            </Button>
          ))}
        <span className="text-muted-foreground ml-auto text-xs">
          {curve.mean.length}점 · 시편 {group.sample_count}개
          {raw.length > 1 && (
            // **줄였다는 것은 화면이 말한다.** 뒤에 깔린 선이 원본 그대로인 줄
            // 알면, 뾰족한 데가 없는 것을 데이터의 성질로 읽는다.
            <> · 뒤의 흐린 선 {raw.length}개가 시편별 원곡선(솎음)</>
          )}
        </span>
      </div>
      <CurveChart
        points={points}
        background={raw}
        // **축에 단위를 붙인다.** 채널 키만 있으면 `stress_true` 가 Pa 인지
        // MPa 인지 화면 어디에도 없다.
        xLabel={axisLabel(curve.x, unitOf(curve.x), dimensionOf(curve.x))}
        yLabel={axisLabel(curve.y, unitOf(curve.y), dimensionOf(curve.y))}
        height={280}
      />
      <p className="text-muted-foreground mt-2 text-xs">
        {single ? (
          <>
            시편 1개의 곡선입니다 — <b>평균이 아니라 그 시편의 값</b>입니다. 이 곡선이{' '}
            <b>피팅의 입력</b>이 되고, 카드에도 시편 1개라고 적힙니다.
          </>
        ) : (
          <>
            점마다 시편 {group.sample_count}개의 {mode === 'mean' ? '평균' : '중앙값'}
            입니다. 이 곡선이 <b>피팅의 입력</b>이 됩니다.
          </>
        )}
      </p>
    </div>
  )
}
