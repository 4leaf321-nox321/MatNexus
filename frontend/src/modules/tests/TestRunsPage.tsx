/**
 * 시험 데이터 목록.
 *
 * 업로드는 202 로 끝나고 파싱은 워커가 한다. 그래서 목록에 **아직 끝나지 않은
 * 시험이 있으면 스스로 갱신한다** — 사용자가 새로고침을 눌러야 상태가 바뀌면,
 * 비동기로 처리하는 이유(요청을 붙잡지 않는 것)의 이득이 사용자에게 안 간다.
 *
 * **등록 진입점이 두 곳이다.** 시험은 시편에 매달리므로 처음에는 재료 상세의
 * 시편 줄에만 두었는데, 그러면 재료 → 재료 상세 → 시료 펼치기 → 시편까지
 * 세 단계를 파고들어야 시작할 수 있다. 실제로 이 화면에 온 사람이 등록 버튼을
 * 찾지 못했다. 화면 이름이 "시험 데이터" 인데 시험을 만들 수 없으면 안 된다.
 *
 * 여기서는 시편을 직접 고르고(`SpecimenPicker`), 시편 줄에서 열 때는 그 단계를
 * 건너뛴다. 같은 다이얼로그가 둘 다 한다 — 업로드 폼을 두 벌 만들면 갈라진다.
 */

import { useEffect, useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronLeft, ChevronRight, FileUp, FlaskConical, Layers, Plus, RefreshCw, Star, Trash2 } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { BatchDialog } from '@/modules/processing/BatchDialog'
import { RUN_STATUS_LABEL, isPending, testsApi } from '@/modules/tests/api'
import { UploadDialog } from '@/modules/tests/UploadDialog'
import { fetchAll } from '@/shared/api/paging'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/shared/components/ui/dropdown-menu'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'

const POLL_MS = 3000

function statusVariant(status: string): 'default' | 'secondary' | 'outline' | 'destructive' {
  if (status === 'failed') return 'destructive'
  if (status === 'parsed') return 'secondary'
  return 'outline'
}

/**
 * 한 쪽에 몇 건. **서버가 200 에서 자른다**(`shared/pagination.py`).
 *
 * 전에는 `limit: 100` 을 박아 두고 총 건수도 안 보여 줬다 — 101번째 시험은
 * **있는데 화면 어디에도 없었고, 없다는 사실조차 안 보였다.** 목록이 조용히
 * 잘리는 것이 가장 나쁘다.
 */
const PAGE_SIZES = [50, 100, 200, 'all'] as const
type PageSize = (typeof PAGE_SIZES)[number]

/**
 * 열 하나를 좁힌다. **개수는 서버가 센다.**
 *
 * 화면이 한 쪽에서 세면 「인장시험 50」이라고 적히는데 실제로는 300건일 수
 * 있고, 그러면 필터 옆의 숫자가 거짓말을 한다.
 *
 * 「전체」가 첫 줄이다 — 고른 것을 푸는 길이 없으면 새로고침으로 푸는 사람이
 * 생긴다.
 */
function ColumnFilter({
  label,
  rows,
  current,
  onPick,
}: {
  label: string
  rows: { key: string; label: string; count: number }[]
  current?: string
  onPick: (value: string | undefined) => void
}) {
  if (rows.length === 0) return <>{label}</>
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="hover:text-foreground -ml-1 inline-flex items-center gap-1 rounded px-1"
        >
          {label}
          {/* **걸린 것이 보여야 한다.** 목록이 왜 짧은지 여기서 설명된다. */}
          {current && <Badge variant="secondary" className="text-[10px]">{current}</Badge>}
          <ChevronDown className="size-3 opacity-60" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-72 overflow-y-auto">
        <DropdownMenuItem onSelect={() => onPick(undefined)}>
          <span className={current ? '' : 'font-medium'}>전체</span>
        </DropdownMenuItem>
        {rows.map((row) => (
          <DropdownMenuItem key={row.key} onSelect={() => onPick(row.key)}>
            <span className={row.key === current ? 'font-medium' : ''}>{row.label}</span>
            <span className="text-muted-foreground ml-auto tabular-nums">{row.count}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export default function TestRunsPage() {
  const { slug } = useParams<{ slug?: string }>()
  const [uploading, setUploading] = useState(false)
  // 사이드바가 '부서' 라고 말하는 화면이므로 그 부서 것만 보여 준다.
  const [size, setSize] = useState<PageSize>(PAGE_SIZES[0])
  const [offset, setOffset] = useState(0)
  const all = size === 'all'
  // **거르는 일은 서버가 한다.** 한 쪽만 받아 화면에서 거르면 뒤엣것이 없는
  // 시험이 된다 — 이 화면의 머리말이 그 이야기다.
  const [filters, setFilters] = useState<Record<string, string | undefined>>({})
  const runs = useResource(
    () =>
      all
        ? fetchAll((limit, from) =>
            testsApi.runs({ workspace: slug, limit, offset: from, ...filters })
          )
        : testsApi.runs({ workspace: slug, limit: size, offset, ...filters }),
    [slug, size, offset, all, filters]
  )
  // 거르기 목록은 필터와 함께 안 바뀐다 — 「무엇이 있나」를 답하는 자리다.
  const facets = useResource(() => testsApi.runFacets(slug), [slug])

  /** 열 하나를 좁힌다. **필터가 바뀌면 처음부터 다시 본다.** */
  function narrow(key: string, value: string | undefined) {
    setOffset(0)
    setPicked(new Set())
    setFilters((current) => ({ ...current, [key]: value }))
  }

  async function removePicked() {
    setBusy(true)
    setFailure(null)
    try {
      const done = await testsApi.removeMany([...picked])
      if (done.blocked.length > 0) {
        // **조용히 세지 않는다.** 무엇이 안 지워졌는지 말해야 다시 고를 수 있다.
        setFailure(
          new Error(
            `${done.deleted}건을 지웠습니다. ${done.blocked.length}건은 권한이 없어 남았습니다.`
          )
        )
      }
      setPicked(new Set())
      setRemoving(false)
      runs.reload()
      facets.reload()
    } catch (caught) {
      setFailure(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }
  const rows = runs.data?.items ?? []
  const total = runs.data?.total ?? 0
  const truncated = all && rows.length < total
  const pending = rows.some((run) => isPending(run.status))

  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [batching, setBatching] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Error | null>(null)
  /** 읽히지 않은 시험은 처리할 곡선이 없다. 고를 수 있게 두면 전부 실패한다. */
  const processable = rows.filter((run) => run.status === 'parsed')
  /** 한 배치는 **한 종류**여야 한다 — 인장 레시피가 DMA 곡선에 걸리면 실패한다. */
  const pickedTypes = new Set(
    rows.filter((run) => picked.has(run.id)).map((run) => run.test_type_key)
  )

  useEffect(() => {
    if (!pending) return
    const timer = setInterval(() => runs.reload(), POLL_MS)
    return () => clearInterval(timer)
  }, [pending, runs])

  return (
    <div>
      <PageHeader
        title="시험 데이터"
        description={`장비 원본을 올리면 서버가 읽어 곡선으로 만듭니다.${
          slug ? ` 이 부서(${slug})가 등록한 시험만 보입니다.` : ''
        }`}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => runs.reload()}>
              <RefreshCw className={`size-4 ${pending ? 'animate-spin' : ''}`} />
              새로고침
            </Button>
            <Button variant="secondary" size="sm" asChild>
              <Link to={`/w/${slug ?? 'default'}/tests/upload`}>
                <FileUp className="size-4" />
                일괄 등록
              </Link>
            </Button>
            <Button size="sm" onClick={() => setUploading(true)}>
              <Plus className="size-4" />
              시험 등록
            </Button>
          </>
        }
      />

      <ErrorNotice error={runs.error ?? facets.error ?? failure} className="mb-4" />

      {/* **고른 게 있을 때만 나타난다.** 늘 떠 있으면 목록의 기본 상태가
          "무언가 골라야 하는 화면" 으로 읽힌다. */}
      {picked.size > 0 && (
        <div className="bg-muted/40 mb-4 flex flex-wrap items-center gap-3 rounded-md border p-3">
          <span className="text-sm">
            <b>{picked.size}건</b> 선택
          </span>
          {pickedTypes.size > 1 && (
            <span className="text-xs text-amber-700 dark:text-amber-500">
              시험 종류가 {pickedTypes.size}가지 섞여 있습니다 — 레시피는 한 종류에 맞춰
              만들어집니다. 종류별로 나눠 거세요.
            </span>
          )}
          <div className="ml-auto flex gap-2">
            <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>
              선택 해제
            </Button>
            <Button
              size="sm"
              onClick={() => setBatching(true)}
              disabled={pickedTypes.size !== 1}
            >
              <Layers className="size-4" />
              레시피 적용
            </Button>
            {/* **여러 건을 한 번에 지운다.** 한 건씩 열어 지우는 것은 일이
                아니다 — 잘못 올린 배치는 통째로 잘못 올라온다. */}
            <Button size="sm" variant="destructive" onClick={() => setRemoving(true)}>
              <Trash2 className="size-4" />
              삭제
            </Button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={removing}
        busy={busy}
        title={`시험 ${picked.size}건을 지웁니다`}
        body={
          <>
            <p className="mb-2">
              고른 <b>{picked.size}건</b>이 목록에서 사라집니다. 원본 파일과 처리 결과도
              함께 가려집니다.
            </p>
            <ul className="text-muted-foreground max-h-40 space-y-0.5 overflow-y-auto font-mono text-xs">
              {rows
                .filter((run) => picked.has(run.id))
                .map((run) => (
                  <li key={run.id}>{run.record_name}</li>
                ))}
            </ul>
          </>
        }
        onConfirm={removePicked}
        onClose={() => setRemoving(false)}
      />

      {batching && (
        <BatchDialog
          testRunIds={[...picked]}
          testTypeKey={[...pickedTypes][0] ?? null}
          onClose={() => {
            setBatching(false)
            setPicked(new Set())
          }}
          // **선택은 닫을 때 푼다.** 돌자마자 풀었더니 다이얼로그가 자기가 방금
          // 무엇을 돌렸는지 잊고 "0건에 레시피 적용" 을 띄웠다 — 결과를 보고
          // 있는 동안 제목이 거짓말을 한다.
          onDone={() => runs.reload()}
        />
      )}

      {pending && (
        <p className="text-muted-foreground mb-3 text-sm">
          읽는 중인 시험이 있어 {POLL_MS / 1000}초마다 상태를 확인합니다.
        </p>
      )}

      {!runs.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          <FlaskConical className="mx-auto mb-2 size-5 opacity-50" />
          등록된 시험이 없습니다.
          <div className="mt-2">
            위의 <span className="text-foreground font-medium">시험 등록</span> 을 누르거나,{' '}
            <Link to="/materials" className="text-primary hover:underline">
              재료 상세
            </Link>{' '}
            의 시편에서 올리세요.
          </div>
        </div>
      )}

      {rows.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              {/* **20건을 하나씩 여는 것은 일이 아니다.** 골라서 한 번에 건다. */}
              <TableHead className="w-8">
                <input
                  type="checkbox"
                  aria-label="전부 선택"
                  checked={picked.size > 0 && picked.size === processable.length}
                  ref={(node) => {
                    if (node) {
                      node.indeterminate = picked.size > 0 && picked.size < processable.length
                    }
                  }}
                  onChange={(event) =>
                    setPicked(
                      event.target.checked ? new Set(processable.map((r) => r.id)) : new Set()
                    )
                  }
                />
              </TableHead>
              <TableHead>이름</TableHead>
              <TableHead>재료</TableHead>
              <TableHead>
                <ColumnFilter
                  label="방향"
                  rows={facets.data?.orientations ?? []}
                  current={filters.orientation}
                  onPick={(value) => narrow('orientation', value)}
                />
              </TableHead>
              <TableHead>
                <ColumnFilter
                  label="종류"
                  rows={facets.data?.test_types ?? []}
                  current={filters.test_type_key}
                  onPick={(value) => narrow('test_type_key', value)}
                />
              </TableHead>
              <TableHead>
                <ColumnFilter
                  label="상태"
                  rows={facets.data?.statuses ?? []}
                  current={filters.status}
                  onPick={(value) => narrow('status', value)}
                />
              </TableHead>
              <TableHead>처리</TableHead>
              <TableHead className="text-right">행</TableHead>
              <TableHead>
                {/* **부서와 다른 축이다.** 부서는 누가 볼 수 있는가를 정하고,
                    사업부는 누가 낸 데이터인가를 적는다. */}
                <ColumnFilter
                  label="사업부"
                  rows={facets.data?.divisions ?? []}
                  current={filters.division}
                  onPick={(value) => narrow('division', value)}
                />
              </TableHead>
              <TableHead>
                <ColumnFilter
                  label="등록한 사람"
                  rows={facets.data?.registrants ?? []}
                  current={filters.registered_by}
                  onPick={(value) => narrow('registered_by', value)}
                />
              </TableHead>
              <TableHead>등록</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((run) => (
              <TableRow key={run.id}>
                <TableCell>
                  <input
                    type="checkbox"
                    aria-label={`${run.record_name} 선택`}
                    disabled={run.status !== 'parsed'}
                    checked={picked.has(run.id)}
                    onChange={(event) =>
                      setPicked((current) => {
                        const next = new Set(current)
                        if (event.target.checked) next.add(run.id)
                        else next.delete(run.id)
                        return next
                      })
                    }
                  />
                </TableCell>
                <TableCell className="font-mono text-xs">
                  <Link to={`/test-runs/${run.id}`} className="hover:text-primary hover:underline">
                    {run.record_name}
                  </Link>
                  {run.warnings.length > 0 && (
                    <AlertTriangle className="ml-1 inline size-3 text-amber-500" />
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground font-mono text-xs">
                  {run.material_name ?? '—'}
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">{run.orientation ?? '—'}</Badge>
                </TableCell>
                <TableCell className="text-sm">{run.test_type_label}</TableCell>
                <TableCell>
                  <Badge variant={statusVariant(run.status)}>
                    {RUN_STATUS_LABEL[run.status] ?? run.status}
                  </Badge>
                  {run.parse_error && (
                    <p className="text-destructive mt-1 max-w-xs text-xs">{run.parse_error}</p>
                  )}
                </TableCell>
                {/* **시편 20개짜리 배치에서 무엇이 남았는지가 여기 보여야 한다.**
                    하나씩 열어 봐야 아는 것은 일이 아니다. 세 상태를 나눈다 —
                    안 했다 / 해 봤는데 안 정했다 / 정했다(ADR 0007). */}
                <TableCell>
                  {run.adopted_result_id ? (
                    <Badge className="gap-1 bg-emerald-600 hover:bg-emerald-600">
                      <Star className="size-3" />
                      채택됨
                    </Badge>
                  ) : run.result_count > 0 ? (
                    <Badge variant="outline" title="돌려는 봤지만 아직 무엇을 쓸지 안 정했습니다">
                      시도 {run.result_count}
                    </Badge>
                  ) : (
                    <span className="text-muted-foreground text-xs">—</span>
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {run.row_count?.toLocaleString('ko-KR') ?? '—'}
                </TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {run.division ?? '—'}
                </TableCell>
                {/* **파일이 이상할 때 물어볼 데가 여기다.** 전에는 상세를
                    열어야 알 수 있었고, 20건이 이상하면 20번 열어야 했다. */}
                <TableCell className="text-muted-foreground text-sm">
                  {run.registered_by ?? '—'}
                </TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {new Date(run.created_at).toLocaleDateString('ko-KR')}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {rows.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
          <span className="text-muted-foreground tabular-nums">
            {all ? `전체 ${rows.length}` : `${offset + 1}–${offset + rows.length}`} /{' '}
            {total}건
          </span>
          <div className="text-muted-foreground flex items-center gap-1">
            <span>한 쪽에</span>
            {PAGE_SIZES.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => {
                  setSize(value)
                  setOffset(0)
                  // 쪽을 넘기면 고른 것이 화면에서 사라진다. 남겨 두면 안 보이는
                  // 시험에 레시피가 걸린다.
                  setPicked(new Set())
                }}
                className={`rounded px-1.5 py-0.5 tabular-nums ${
                  size === value ? 'bg-muted text-foreground font-medium' : 'hover:bg-muted/60'
                }`}
              >
                {value === 'all' ? '전체' : value}
              </button>
            ))}
          </div>
          {!all && (
          <div className="ml-auto flex gap-1">
            <Button
              size="sm"
              variant="outline"
              disabled={offset === 0}
              onClick={() => {
                setOffset(Math.max(0, offset - size))
                setPicked(new Set())
              }}
            >
              <ChevronLeft className="size-3.5" />
              이전
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={offset + rows.length >= total}
              onClick={() => {
                setOffset(offset + size)
                setPicked(new Set())
              }}
            >
              다음
              <ChevronRight className="size-3.5" />
            </Button>
          </div>
          )}
        </div>
      )}

      {/* **조용히 자르지 않는다.** 천장에 걸렸으면 그 사실을 적는다. */}
      {truncated && (
        <p className="mt-2 text-xs text-amber-700 dark:text-amber-500">
          {total}건 중 {rows.length}건까지만 한 번에 보여 줍니다 — 표가 그보다 길면
          브라우저가 버겁습니다. 부서나 상태로 좁히세요.
        </p>
      )}

      <UploadDialog
        open={uploading}
        onClose={() => setUploading(false)}
        onDone={() => {
          setUploading(false)
          runs.reload()
        }}
      />
    </div>
  )
}
