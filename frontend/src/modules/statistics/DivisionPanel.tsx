/**
 * 사업부별 현황 — **왼쪽 표, 오른쪽 연간 그래프.**
 *
 * 사업부는 시험에만 붙는다(ADR 0010 의 축). 재료·시편에는 사업부 칸이 없으므로
 * 여기의 재료·시료·시편 수는 **그 사업부의 시험이 걸친 것**이다 — 같은 재료를 두
 * 사업부가 시험하는 것이 정상이라, 열끼리 합치면 전체보다 클 수 있다.
 *
 * 순서는 서버가 정한다(MX · VD · DA · NW · 의료기기 — 실사용 요청으로 고정).
 * 「미지정」 이 보이면 그건 채울 일이 남았다는 뜻이다 — 숨기지 않는다.
 */

import { Suspense, lazy } from 'react'

import type { DivisionOverview } from '@/modules/statistics/api'
import { colorOf } from '@/modules/statistics/divisionColors'
import { Skeleton } from '@/shared/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'

// **recharts 는 늦게 온다.** 홈은 로그인 직후 첫 화면이라 그 무게를 첫 페인트에
// 물리지 않는다 — 표는 즉시 그리고 그래프만 뒤따른다.
const DivisionYearChart = lazy(() => import('@/modules/statistics/DivisionYearChart'))

export function DivisionPanel({
  data,
  loading,
}: {
  data: DivisionOverview | null
  loading: boolean
}) {
  if (loading && !data) return <Skeleton className="h-40" />
  if (!data || data.divisions.length === 0) return null

  const order = data.divisions.map((row) => row.division)

  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold">사업부별 현황</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>사업부</TableHead>
                  <TableHead className="text-right">재료</TableHead>
                  <TableHead className="text-right">시료</TableHead>
                  <TableHead className="text-right">시편</TableHead>
                  <TableHead className="text-right">시험</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.divisions.map((row) => (
                  <TableRow key={row.division}>
                    <TableCell
                      className={
                        row.division === '미지정' ? 'text-muted-foreground' : 'font-medium'
                      }
                    >
                      <span
                        className="mr-1.5 inline-block size-2 rounded-full align-middle"
                        style={{ backgroundColor: colorOf(row.division, order) }}
                      />
                      {row.division}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{row.material_count}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.sample_count}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.specimen_count}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.run_count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-muted-foreground mt-1 text-xs">
            재료·시료·시편은 그 사업부의 시험이 걸친 수 — 같은 재료를 여러 사업부가 시험할 수 있어
            합계가 전체보다 클 수 있습니다.
          </p>
        </div>
        <Suspense fallback={<Skeleton className="h-40" />}>
          <DivisionYearChart data={data} order={order} />
        </Suspense>
      </div>
    </section>
  )
}
