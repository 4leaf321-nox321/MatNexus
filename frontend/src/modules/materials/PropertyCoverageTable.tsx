/**
 * 물성 지도 — **이 재료에 어떤 물성이 어떤 조건에 어떤 등급으로 있나, 한 장.**
 *
 * 시험으로 잰 값 · 사람이 적은 선언 · 이어진 문헌값을 물성 하나 아래 같은 줄 모양으로 편다.
 * 전에는 세 곳을 각자 열어 봐야 했다. 공용어(문헌 물성 키)에 안 이어진 스칼라·항목은
 * 「안 이어진 것」 으로 함께 보인다 — 지도에서 사라지면 없는 줄 안다.
 *
 * 값은 SI 로 오고 표는 표시 단위로 바꿔 보인다(`shared/units`). 등급은 문헌·사내가 같은
 * 1~4 척도다 — 1 이 가장 좋다.
 */

import { materialsApi } from '@/modules/materials/api'
import type { CoverageEntry, PropertyCoverage } from '@/modules/materials/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'
import { formatScalar } from '@/shared/units'

const ORIGIN_LABEL: Record<string, string> = {
  measured: '시험',
  internal: '선언',
  catalog: '문헌',
}

const CONDITION_LABEL: Record<string, string> = {
  temperature: '온도',
  strain_rate: '변형률속도',
  frequency: '주파수',
  humidity: '상대습도',
  pressure: '압력',
  crosshead_speed: '속도',
  preload: '예하중',
  aging_time: '노화 시간',
}

/** 표준 조건 키 → 저장 단위(SI). 표시 단위·환산은 `shared/units` 표가 정한다. */
const CONDITION_SI: Record<string, string> = {
  temperature: 'K',
  strain_rate: '1/s',
  frequency: 'Hz',
  humidity: '1',
  pressure: 'Pa',
  crosshead_speed: 'm/s',
  preload: 'N',
  aging_time: 's',
}

/** 조건 한 벌을 사람 말로 — 단위 표가 온도를 °C 로 바꾼다. 없으면 「조건 없음」. */
function conditionText(conditions: Record<string, number>): string {
  return Object.entries(conditions)
    .map(([key, value]) => `${CONDITION_LABEL[key] ?? key} ${formatScalar(value, CONDITION_SI[key])}`)
    .join(' · ')
}

function EntryRow({
  entry,
  siUnit,
  first,
  span,
  name,
}: {
  entry: CoverageEntry
  siUnit: string | null
  first: boolean
  span: number
  name: string
}) {
  const shown = siUnit ? formatScalar(entry.value_si, siUnit) : `${entry.value_si}`
  const conditions = conditionText(entry.conditions)
  return (
    <TableRow>
      {first && (
        <TableCell rowSpan={span} className="align-top font-medium">
          {name}
        </TableCell>
      )}
      <TableCell>
        <Badge variant={entry.origin === 'measured' ? 'default' : 'secondary'}>
          {ORIGIN_LABEL[entry.origin] ?? entry.origin}
        </Badge>
      </TableCell>
      <TableCell className="tabular-nums">등급 {entry.tier}</TableCell>
      <TableCell className="tabular-nums">
        {shown}
        {entry.count > 1 && (
          <span className="text-muted-foreground"> · 표본 {entry.count}</span>
        )}
      </TableCell>
      <TableCell>
        {conditions || <span className="text-muted-foreground">조건 없음</span>}
      </TableCell>
      <TableCell>
        <span>{entry.ref_label}</span>
        {entry.method && <span className="text-muted-foreground"> · {entry.method}</span>}
      </TableCell>
    </TableRow>
  )
}

export function PropertyCoverageTable({ materialId }: { materialId: string }) {
  const coverage = useResource<PropertyCoverage>(
    () => materialsApi.propertyCoverage(materialId),
    [materialId],
  )
  const data = coverage.data
  const unmapped = data
    ? [...(data.unmapped.scalars ?? []), ...(data.unmapped.items ?? [])]
    : []

  return (
    <section className="space-y-3">
      <p className="text-muted-foreground text-xs">
        시험으로 잰 값 · 적어 둔 값 · 이어진 문헌값을 물성마다 한 줄씩. 등급은 1 이 가장
        좋습니다(실측·표본 3 이상) — 문헌과 같은 척도입니다.
      </p>
      <ErrorNotice error={coverage.error} />
      {data && data.properties.length === 0 && (
        <p className="text-muted-foreground rounded-md border py-6 text-center text-sm">
          이 재료에는 아직 값이 없습니다 — 시험을 등록하거나 재료 기본 정보 카드로 적어
          넣으면 여기 섭니다.
        </p>
      )}
      {data && data.properties.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table className="text-sm">
            <TableHeader>
              <TableRow>
                <TableHead>물성</TableHead>
                <TableHead>출처</TableHead>
                <TableHead>등급</TableHead>
                <TableHead>값</TableHead>
                <TableHead>조건</TableHead>
                <TableHead>어디서</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.properties.map((row) =>
                row.entries.map((entry, index) => (
                  <EntryRow
                    key={`${row.key}-${entry.ref_kind}-${entry.ref_id}-${index}`}
                    entry={entry}
                    siUnit={row.si_unit}
                    first={index === 0}
                    span={row.entries.length}
                    name={row.name}
                  />
                )),
              )}
            </TableBody>
          </Table>
        </div>
      )}
      {unmapped.length > 0 && (
        <p className="text-muted-foreground text-xs" data-testid="coverage-unmapped">
          공용어에 안 이어져 지도에 못 선 것: {unmapped.join(', ')} — 기준정보 &gt; 물성 매핑에서
          이으면 보입니다.
        </p>
      )}
    </section>
  )
}
