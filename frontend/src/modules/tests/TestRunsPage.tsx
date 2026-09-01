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
import { AlertTriangle, ArrowDown, ArrowUp, ChevronDown, ChevronsUpDown, ChevronLeft, ChevronRight, FileUp, FlaskConical, Layers, PencilLine, Plus, RefreshCw, Search, Star, Trash2, X } from 'lucide-react'
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom'

import { BatchDialog } from '@/modules/processing/BatchDialog'
import { RUN_STATUS_LABEL, isPending, testsApi } from '@/modules/tests/api'
import { UploadDialog } from '@/modules/tests/UploadDialog'
import { fetchAll } from '@/shared/api/paging'
import { AddToBasket } from '@/shared/components/AddToBasket'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { SortButton } from '@/shared/components/ColumnFilter'
import type { SortHandle } from '@/shared/components/ColumnFilter'
import { Stamp } from '@/shared/components/Stamp'
import { PageHeader } from '@/shared/components/PageHeader'
import { BulkEditDialog } from '@/modules/tests/BulkEditDialog'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
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
import { useRowSelection } from '@/shared/hooks/useRowSelection'
import { useSort } from '@/shared/hooks/useSort'

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
/** 이름 옆에 서는 정렬 화살표. **꺼져 있을 때도 보인다** — 안 보이면 누를 수
 *  있는 줄인지 모르고, 그러면 정렬이 있어도 아무도 안 쓴다. */
function SortArrow({ sort }: { sort: SortHandle }) {
  const on = sort.active === sort.key
  const Icon = on ? (sort.descending ? ArrowDown : ArrowUp) : ChevronsUpDown
  return (
    <button
      type="button"
      aria-label={`${sort.key} 로 정렬`}
      aria-pressed={on}
      className={`hover:text-foreground rounded ${on ? 'text-foreground' : 'opacity-40'}`}
      onClick={() => sort.onSort(sort.key)}
    >
      <Icon className="size-3" aria-hidden />
    </button>
  )
}

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
  sort,
}: {
  label: string
  rows: { key: string; label: string; count: number }[]
  current?: string
  onPick: (value: string | undefined) => void
  /** 주면 이름 옆에 정렬 화살표가 선다. **이름을 겸하게 둘 수 없다** — 이
   *  표의 거르기는 드롭다운이라 이름을 누르면 그것이 열린다. */
  sort?: SortHandle
}) {
  const arrow = sort ? <SortArrow sort={sort} /> : null
  if (rows.length === 0)
    return (
      <span className="inline-flex items-center gap-1">
        {label}
        {arrow}
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1">
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
    {arrow}
    </span>
  )
}

export default function TestRunsPage() {
  const { slug } = useParams<{ slug?: string }>()
  // 지금 이 목록의 주소. 상세로 넘겨 「뒤로」 가 여기로 돌아오게 한다.
  const { pathname } = useLocation()
  const [uploading, setUploading] = useState(false)
  // 사이드바가 '부서' 라고 말하는 화면이므로 그 부서 것만 보여 준다.
  const [size, setSize] = useState<PageSize>(PAGE_SIZES[0])
  const [offset, setOffset] = useState(0)
  const all = size === 'all'
  // **거르는 일은 서버가 한다.** 한 쪽만 받아 화면에서 거르면 뒤엣것이 없는
  // 시험이 된다 — 이 화면의 머리말이 그 이야기다.
  // **주소로 걸러서 들어올 수 있다.** 홈의 「읽기 실패 N」 이 `?status=failed` 로
  // 보내는데 그것을 안 읽으면 거르개 없는 전체 목록이 뜬다 — 누른 사람은 그 숫자가
  // 가리킨 것을 다시 찾아야 하고, 단추가 안 먹은 것처럼 보인다.
  const [askedIn] = useSearchParams()
  const [filters, setFilters] = useState<Record<string, string | undefined>>(() => {
    // 재료 화면의 「그 시험 보기」 가 `?material=` 로, 홈의 「읽기 실패 N」 이
    // `?status=` 로 보낸다. 안 읽으면 거르개 없는 전체가 떠서, 세어 준 값을 사람이
    // 다시 찾아야 한다.
    const asked: Record<string, string | undefined> = {}
    const status = askedIn.get('status')
    const material = askedIn.get('material')
    if (status) asked.status = status
    if (material) asked.material_id = material
    return asked
  })
  /**
   * 찾기 상자에 **치는 중**인 글자와 **적용된** 글자를 가른다.
   *
   * 한 글자마다 목록을 다시 부르면 233건짜리 화면에서도 요청이 줄줄이 나가고,
   * 늦게 온 응답이 최신 결과를 덮는다. 재료 목록과 같은 방식이다 — 엔터나
   * 「찾기」 를 누를 때만 간다.
   */
  const [query, setQuery] = useState('')
  // 기본은 **최근 등록순.** 전에도 그랬고, 이제 다른 열로도 바꿀 수 있다.
  const { sort, handle } = useSort('created_at', {
    // **이 브라우저가 기억한다.** 계정이 아니다 — 같은 PC 를 다른 사람이
    // 쓰면 앞사람 설정이 보인다. 정렬은 데이터가 아니라 보는 방식이라
    // 새어도 잃을 것이 없다.
    remember: 'runs',
    // **저장된 열이 지금도 정렬 가능한지 확인한다.** 표에서 열을 빼면
    // 서버가 422 를 내고, 그러면 그 브라우저에서만 목록이 영영 안 뜬다.
    allowed: ['created_at', 'record_name', 'tested_at', 'operator', 'instrument', 'division', 'status'],
  })

  const runs = useResource(
    () =>
      all
        ? fetchAll((limit, from) =>
            testsApi.runs({
              workspace: slug,
              limit,
              offset: from,
              sort: sort.key,
              desc: sort.descending,
              ...filters,
            })
          )
        : testsApi.runs({
            workspace: slug,
            limit: size,
            offset,
            sort: sort.key,
            desc: sort.descending,
            ...filters,
          }),
    [slug, size, offset, all, filters, sort]
  )
  // 거르기 목록은 필터와 함께 안 바뀐다 — 「무엇이 있나」를 답하는 자리다.
  const facets = useResource(() => testsApi.runFacets(slug), [slug])

  /** 찾기 상자가 적용한 글자. `filters` 에 섞어 두면 열 필터와 함께 흐른다. */
  function search(text: string) {
    setOffset(0)
    selection.clear()
    // 빈 글자는 **아예 안 보낸다** — `q=` 를 보내면 서버가 빈 조건으로 한 번 더
    // 훑는다. 지운 것과 안 친 것을 같게 본다.
    setFilters((current) => ({ ...current, q: text || undefined }))
  }

  /** 열 하나를 좁힌다. **필터가 바뀌면 처음부터 다시 본다.** */
  function narrow(key: string, value: string | undefined) {
    setOffset(0)
    selection.clear()
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
      selection.clear()
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

  const [editing, setEditing] = useState(false)
  const [batching, setBatching] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Error | null>(null)
  /** 읽히지 않은 시험은 처리할 곡선이 없다. 고를 수 있게 두면 전부 실패한다. */
  const processable = rows.filter((run) => run.status === 'parsed')
  // **고를 수 있는 줄만 넘긴다.** Shift 범위가 못 고르는 줄을 건너뛰어야 한다 —
  // 안 그러면 범위 안의 실패한 시험까지 켜지고, 배치가 통째로 실패한다.
  const selection = useRowSelection(processable.map((run) => run.id))
  const picked = selection.picked
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

      {/* **이름 하나로 재료·시료·시편·회차가 다 걸린다.** `record_name` 이
          그 넷을 조합해 만들어지기 때문이다(`matcore/naming.py`). 그래서 열
          필터와 성격이 다르다 — 열 필터는 「이 열이 이 값인 것」 이고, 이건
          「어디든 이 글자가 있는 것」 이다. 그래서 표 위에 따로 둔다. */}
      <form
        className="mb-4 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          search(query.trim())
        }}
      >
        <div className="relative flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="재료 · 시편 · 시험 이름 · 원본 파일명으로 찾기"
            className="pl-9"
            aria-label="시험 찾기"
          />
        </div>
        {/* **지우는 길을 둔다.** 상자를 비우고 엔터를 치면 되지만, 찾은 뒤에는
            상자에 글자가 남아 있어 「지금 걸러진 상태인가」 가 헷갈린다. */}
        {filters.q && (
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setQuery('')
              search('')
            }}
          >
            <X className="size-4" />
            지우기
          </Button>
        )}
        <Button type="submit" variant="secondary">
          찾기
        </Button>
      </form>

      {filters.q && (
        <p className="text-muted-foreground mb-3 text-sm">
          <b className="text-foreground">{filters.q}</b> 로 좁힌 {total}건입니다.
        </p>
      )}

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
          {/* **담아 두면 화면을 오가지 않아도 된다**(ADR 0024). 여기서 고른 것을
              워크벤치가 이어받는다.

              **이 줄에 그려지지 않는다** — 떠 있는 패널로 화면 위에 뜬다. 이 줄에
              단추로 세워 봤더니(v1.174~1.178) 색을 채우고 자리를 옮겨도 못 찾았다:
              처리 단추가 넷 늘어선 줄에서 다섯째 단추는 눈에 안 들어온다. */}
          <AddToBasket
            kind="test_run"
            ids={[...picked]}
            labels={rows.filter((one) => picked.has(one.id)).map((one) => one.record_name)}
            workspaceSlug={slug}
          />

          <div className="ml-auto flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={() => selection.clear()}>
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
            {/* **올릴 때 빠뜨린 것을 나중에 채운다.** 지금까지는 사업부를
                빠뜨리면 다시 올리는 수밖에 없었다. */}
            <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
              <PencilLine className="size-4" />
              일괄 수정
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

      <BulkEditDialog
        open={editing}
        runIds={[...picked]}
        onClose={() => setEditing(false)}
        onDone={() => {
          runs.reload()
          // 사업부를 바꾸면 거를 수 있는 목록도 바뀐다 — 안 다시 읽으면 방금
          // 넣은 값으로 거를 수 없다.
          facets.reload()
        }}
      />

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
            selection.clear()
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
                  checked={selection.allOn}
                  ref={(node) => {
                    if (node) node.indeterminate = selection.someOn
                  }}
                  onChange={(event) => selection.setAll(event.target.checked)}
                />
              </TableHead>
              <TableHead>
                <SortButton label="이름" sort={handle('record_name')} />
              </TableHead>
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
                  sort={handle('status')}
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
                  sort={handle('division')}
                  rows={facets.data?.divisions ?? []}
                  current={filters.division}
                  onPick={(value) => narrow('division', value)}
                />
              </TableHead>
              <TableHead>
                {/* **묶어 보려고 적는 값이다.** 조건이지만 단위가 없는 글자라
                    목록에서 그대로 보인다 — 「2026 고온」 이 몇 건인지 세려고
                    상세를 하나씩 열게 하지 않는다. */}
                <ColumnFilter
                  label="시험 그룹"
                  rows={facets.data?.testing_groups ?? []}
                  current={filters.testing_group}
                  onPick={(value) => narrow('testing_group', value)}
                />
              </TableHead>
              <TableHead>
                {/* **등록한 사람과 다르다.** 등록은 파일을 올린 사람이고,
                    시험자는 실제로 장비를 돌린 사람이다 — 물어볼 데가 다르다. */}
                <ColumnFilter
                  label="시험자"
                  rows={facets.data?.operators ?? []}
                  current={filters.operator}
                  onPick={(value) => narrow('operator', value)}
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
              <TableHead>
                <SortButton label="등록 일시" sort={handle('created_at')} />
              </TableHead>
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
                    // **`onClick` 이다.** `onChange` 이벤트에는 shiftKey 가 없다 —
                    // 브라우저가 만들어 내는 합성 이벤트라 누른 키가 안 실린다.
                    onClick={(event) => selection.toggle(run.id, event)}
                    onChange={() => {}}
                  />
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {/* **어디서 왔는지 함께 넘긴다.** 상세의 「뒤로」 가 늘 재료
                      화면으로 갔는데, 목록에서 들어온 사람은 목록으로 돌아가려
                      한다 — 20건을 훑는 중이면 재료로 튕기는 순간 자리를 잃는다. */}
                  <Link
                    to={`/test-runs/${run.id}`}
                    state={{ from: { to: pathname, label: '시험 데이터' } }}
                    className="hover:text-primary hover:underline"
                  >
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
                <TableCell className="text-muted-foreground text-sm">
                  {typeof run.conditions?.testing_group === 'string'
                    ? run.conditions.testing_group
                    : '—'}
                </TableCell>
                {/* **파일이 이상할 때 물어볼 데가 여기다.** 전에는 상세를
                    열어야 알 수 있었고, 20건이 이상하면 20번 열어야 했다. */}
                <TableCell className="text-muted-foreground text-sm">
                  {run.operator ?? '—'}
                </TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {run.registered_by ?? '—'}
                </TableCell>
                <TableCell>
                  {/* **같은 날 여러 번 올린다.** 배치로 들어오면 날짜만으로는
                      어느 것이 나중 것인지 표만 봐서는 모른다. */}
                  <Stamp at={run.created_at} />
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
                  selection.clear()
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
                selection.clear()
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
                selection.clear()
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
