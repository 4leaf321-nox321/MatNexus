/**
 * 사업부별 현황 — **누가 무엇을 얼마나 시험했나.**
 *
 * 사업부는 시험에만 붙는다(ADR 0010 의 축). 재료·시편에는 사업부 칸이 없으므로
 * 여기의 재료·시료·시편 수는 **그 사업부의 시험이 걸친 것**이다 — 같은 재료를 두
 * 사업부가 시험하는 것이 정상이라, 열끼리 합치면 전체보다 클 수 있다.
 *
 * 「미지정」 이 보이면 그건 채울 일이 남았다는 뜻이다 — 숨기지 않는다.
 */

import type { DivisionTally } from '@/modules/statistics/api'
import { Skeleton } from '@/shared/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'

export function DivisionPanel({
  data,
  loading,
}: {
  data: DivisionTally[] | null
  loading: boolean
}) {
  if (loading && !data) return <Skeleton className="h-32" />
  if (!data || data.length === 0) return null

  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold">사업부별 현황</h2>
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
            {data.map((row) => (
              <TableRow key={row.division}>
                <TableCell
                  className={
                    row.division === '미지정' ? 'text-muted-foreground' : 'font-medium'
                  }
                >
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
        재료·시료·시편은 그 사업부의 시험이 걸친 수 — 같은 재료를 여러 사업부가 시험할 수
        있어 합계가 전체보다 클 수 있습니다.
      </p>
    </section>
  )
}
