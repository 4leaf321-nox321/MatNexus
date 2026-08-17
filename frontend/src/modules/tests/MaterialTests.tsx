/**
 * 이 재료의 시험 — **평면 목록.**
 *
 * 계층 화면(시료 → 시편 → 시험)은 "무엇이 어디에 매달려 있나" 에 답하지만,
 * **"이 재료에 시험이 몇 건 들어왔나"** 에는 답하지 못한다. 시편이 11개면 시험
 * 11건이 11군데로 흩어지고, 실패한 것이 있는지 보려면 전부 펼쳐야 한다.
 *
 * 그래서 같은 데이터를 한 번 더, 이번에는 평면으로 준다. 계층을 없애는 것이
 * 아니라 **묻는 질문이 다른 것**이다.
 *
 * 등록은 여기서 하지 않는다. 시험은 시편에 매달리고(단면적과 방향이 거기 있다),
 * 어느 시편인지 고르는 자리는 계층 화면이다.
 */

import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, FlaskConical } from 'lucide-react'
import { Link } from 'react-router-dom'

import { RUN_STATUS_LABEL, isPending, testsApi } from '@/modules/tests/api'
import type { TestRun } from '@/modules/tests/api'
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

/** 서버가 강제하는 목록 상한과 같은 값. 넘으면 넘었다고 말한다. */
const PAGE = 200

const FILTERS = [
  { key: '', label: '전체' },
  { key: 'parsed', label: '완료' },
  { key: 'failed', label: '실패' },
] as const

interface Props {
  materialId: string
}

export function MaterialTests({ materialId }: Props) {
  const [status, setStatus] = useState<string>('')
  const runs = useResource(
    () =>
      testsApi.runs({
        material_id: materialId,
        ...(status ? { status: status as 'parsed' | 'failed' } : {}),
        limit: PAGE,
      }),
    [materialId, status]
  )
  const rows = runs.data?.items ?? []
  const total = runs.data?.total ?? 0
  const pending = rows.some((run) => isPending(run.status))

  // 올린 직후에는 아직 읽는 중이다. 새로고침을 눌러야 보이면 비동기의 이득이
  // 사용자에게 가지 않는다.
  useEffect(() => {
    if (!pending) return
    const timer = setInterval(() => runs.reload(), 3000)
    return () => clearInterval(timer)
  }, [pending, runs])

  const failed = rows.filter((run) => run.status === 'failed').length
  const adopted = rows.filter((run) => run.adopted_result_id).length

  return (
    <section>
      <ErrorNotice error={runs.error} className="mb-4" />

      {/* 옆 탭과 무엇이 다른지 한 줄로 말한다. 인장에서는 시편과 시험이 1:1 이라
          둘이 같은 것처럼 보이는데, DMA·피로처럼 시편 하나를 여러 번 거는 시험도
          있어서 층을 합칠 수 없다. */}
      <p className="text-muted-foreground mb-3 rounded-md border border-dashed p-2.5 text-xs">
        <b>시험</b>은 시편 하나를 장비에 건 기록입니다 — 장비 파일 하나가 시험 한
        건입니다. 인장은 시편이 파단되어 한 번뿐이라 시편과 1:1 이지만, DMA·피로는
        시편 하나에 여러 건이 붙습니다.
      </p>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        {FILTERS.map((item) => (
          <Button
            key={item.key || 'all'}
            size="sm"
            variant={status === item.key ? 'default' : 'outline'}
            onClick={() => setStatus(item.key)}
          >
            {item.label}
          </Button>
        ))}
        <span className="text-muted-foreground ml-auto text-sm">
          {/* **이 세 숫자가 이 탭의 존재 이유다.** 계층 화면에서는 시편을 전부
              펼쳐야 셀 수 있다. */}
          {total}건{failed > 0 && ` · 실패 ${failed}`}
          {` · 채택 ${adopted}`}
          {pending && ' · 읽는 중'}
        </span>
      </div>

      {!runs.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          <FlaskConical className="mx-auto mb-2 size-5 opacity-50" />
          {status ? '해당하는 시험이 없습니다.' : '아직 시험이 없습니다.'}
          {!status && (
            <p className="mt-1">
              시험은 시편에 파일을 올려 등록합니다 — <b>시료·시편</b> 탭에서 시편을
              펼치고 <b>시험 등록</b>을 누르세요.
            </p>
          )}
        </div>
      )}

      {rows.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>시편</TableHead>
              <TableHead>시험</TableHead>
              <TableHead>상태</TableHead>
              <TableHead className="text-right">행</TableHead>
              <TableHead>처리</TableHead>
              <TableHead>등록</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((run) => (
              <RunRow key={run.id} run={run} />
            ))}
          </TableBody>
        </Table>
      )}

      {total > rows.length && (
        // **잘렸으면 잘렸다고 말한다.** 조용히 앞의 200건만 보여 주면 "왜 그
        // 시험이 없지" 를 아무도 설명하지 못한다.
        <p className="text-muted-foreground mt-3 text-xs">
          {total}건 중 {rows.length}건을 보이고 있습니다. 서버가 목록에 상한을 둡니다 —
          전체는 <b>시험 데이터</b> 화면에서 보세요.
        </p>
      )}
    </section>
  )
}

function RunRow({ run }: { run: TestRun }) {
  return (
    <TableRow>
      <TableCell>
        <div className="flex items-center gap-2">
          {run.orientation && <Badge variant="secondary">{run.orientation}</Badge>}
          <span className="text-muted-foreground font-mono text-xs">
            {/* 이름이 길다. 재료 이름은 이 화면에서 이미 아는 값이라 뒤만 보인다. */}
            {run.specimen_name?.split('__').slice(-1)[0] ?? '—'}
          </span>
        </div>
      </TableCell>

      <TableCell>
        <Link
          to={`/test-runs/${run.id}`}
          className="hover:text-primary font-mono text-xs hover:underline"
        >
          {run.record_name.split('__').slice(-1)[0]}
        </Link>
        {run.warnings.length > 0 && (
          <span className="ml-2 inline-flex items-center gap-1 text-xs text-amber-700 dark:text-amber-500">
            <AlertTriangle className="size-3" />
            {run.warnings.length}
          </span>
        )}
      </TableCell>

      <TableCell>
        <Badge
          variant={
            run.status === 'failed'
              ? 'destructive'
              : run.status === 'parsed'
                ? 'secondary'
                : 'outline'
          }
        >
          {RUN_STATUS_LABEL[run.status] ?? run.status}
        </Badge>
        {/* **왜 실패했는지 목록에서 보여야 한다.** 열어 봐야 아는 것은 일이다. */}
        {run.parse_error && (
          <p className="text-muted-foreground mt-0.5 max-w-xs truncate text-xs">
            {run.parse_error}
          </p>
        )}
      </TableCell>

      <TableCell className="text-right tabular-nums">
        {run.row_count == null ? '—' : run.row_count.toLocaleString('ko-KR')}
      </TableCell>

      <TableCell>
        {run.adopted_result_id ? (
          // 채택은 '이 시험의 물성이 정해졌다' 는 뜻이다(ADR 0007). 통계와 적합에
          // 들어가는 것이 이것뿐이라 목록에서 바로 보여야 한다.
          <span className="inline-flex items-center gap-1 text-xs text-emerald-700 dark:text-emerald-500">
            <CheckCircle2 className="size-3.5" />
            채택됨
          </span>
        ) : run.result_count > 0 ? (
          <span className="text-muted-foreground text-xs">
            결과 {run.result_count}건 · 미채택
          </span>
        ) : (
          <span className="text-muted-foreground text-xs">—</span>
        )}
      </TableCell>

      <TableCell className="text-muted-foreground text-xs">
        {new Date(run.created_at).toLocaleDateString('ko-KR')}
      </TableCell>
    </TableRow>
  )
}
