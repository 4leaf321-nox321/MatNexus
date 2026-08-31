/**
 * 재료 카탈로그 — 목록·검색·등록.
 *
 * 등록 폼에 **이름 미리보기**가 있다. 값을 넣는 동안 서버가 만들 이름을 그대로
 * 보여 주고, 이미 쓰이는 이름이면 저장 전에 알려 준다. 화면이 이름 규칙을 다시
 * 구현하지 않는 것이 핵심이다 — 기존 앱은 화면(DOM)이 ID를 만들어서 서버·배치가
 * 같은 이름을 만들 방법 자체가 없었다(ADR 0004).
 */

import { useState } from 'react'
import {
  Boxes,
  ChevronLeft,
  ChevronRight,
  Globe2,
  Plus,
  Search,
  Trash2,
  TriangleAlert,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { materialsApi } from '@/modules/materials/api'
import type { BulkDeletePlan } from '@/modules/materials/api'
import { categoriesOf, familiesOf } from '@/modules/materials/classification'
import { BulkMaterialDialog } from '@/modules/materials/BulkMaterialDialog'
import { NewMaterialDialog } from '@/modules/materials/NewMaterialDialog'
import { fetchAll } from '@/shared/api/paging'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import {
  ColumnFilter,
  ColumnLabel,
  FILTER_HEAD,
  FILTER_ROW,
} from '@/shared/components/ColumnFilter'
import { PageHeader } from '@/shared/components/PageHeader'
import { Stamp } from '@/shared/components/Stamp'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
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

/**
 * 한 쪽에 몇 건. `'all'` 은 200건씩 이어 받아 모은다(`shared/api/paging.ts`).
 *
 * **서버 상한을 올리지 않는다.** 올리면 언젠가 `?limit=1000000` 이 나가고,
 * 악의가 없어도 그렇게 된다 — 화면이 '전부' 를 구현하면서 큰 수를 넣기 때문이다.
 */
const PAGE_SIZES = [50, 100, 200, 'all'] as const
type PageSize = (typeof PAGE_SIZES)[number]

export default function MaterialsPage() {
  const [query, setQuery] = useState('')
  const [applied, setApplied] = useState('')
  const [registering, setRegistering] = useState(false)
  const [bulk, setBulk] = useState(false)
  const [size, setSize] = useState<PageSize>(PAGE_SIZES[0])
  const [offset, setOffset] = useState(0)
  const [family, setFamily] = useState('')
  const [category, setCategory] = useState('')
  // 열 머리에서 거르는 것들. `q` 와 달리 **그 열만** 본다.
  const [name, setName] = useState('')
  const [alias, setAlias] = useState('')
  // **소속은 부서다.** 「전역인가 아닌가」 만 갈랐더니 부서가 여럿인 곳에서
  // 「고분자팀 재료」 를 못 찾았다(실사용 지적). 값은 `global` 이거나 부서 slug.
  const [scope, setScope] = useState('')
  // 기본은 **최근 등록순.** 전에는 이름순이었는데, 갓 넣은 것을 찾으려면
  // 표를 훑어야 했다 — 등록 직후에 보는 일이 가장 잦다.
  const { sort, handle } = useSort('created_at', {
    // **이 브라우저가 기억한다.** 계정이 아니다 — 같은 PC 를 다른 사람이
    // 쓰면 앞사람 설정이 보인다. 정렬은 데이터가 아니라 보는 방식이라
    // 새어도 잃을 것이 없다.
    remember: 'materials',
    // **저장된 열이 지금도 정렬 가능한지 확인한다.** 표에서 열을 빼면
    // 서버가 422 를 내고, 그러면 그 브라우저에서만 목록이 영영 안 뜬다.
    allowed: ['created_at', 'record_name', 'alias', 'family', 'category', 'spec_thickness'],
  })
  const [removing, setRemoving] = useState(false)
  // 아래(시료·시편·시험)까지 함께 지울지. **기본은 안 지우는 쪽이다** — 고르고
  // 지우기를 누르는 것이 갑자기 트리를 날리는 뜻이 되면 안 된다.
  const [cascade, setCascade] = useState(false)
  const [withRuns, setWithRuns] = useState(false)
  const [plan, setPlan] = useState<BulkDeletePlan | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Error | null>(null)
  const all = size === 'all'

  // 무엇으로 거를 수 있는지는 **데이터가 정한다.** 목록에 실제로 있는 조합만 준다.
  const classes = useResource(() => materialsApi.classifications(), [])
  const rowsOf = classes.data ?? []
  // 세는 규칙은 옆패널과 **같은 것을 쓴다**(`classification.ts`).
  const families = familiesOf(rowsOf)
  const categories = categoriesOf(rowsOf, family)

  const filters = {
    q: applied,
    name,
    alias,
    family,
    category,
    // 값이 `global` 이면 전역만, 부서 slug 면 그 부서만. 서버가 둘을 다른 칸으로
    // 받는다 — 「전역」 은 소유가 없는 것이라 부서 목록에 낄 수 없다.
    scope: (scope === 'global' ? 'global' : undefined) as 'global' | undefined,
    workspace: scope && scope !== 'global' ? scope : undefined,
    sort: sort.key,
    desc: sort.descending,
  }

  // 소속 거르기의 선택지. **부서 이름을 보여야** 「고분자팀 재료」 를 고를 수 있다.
  const workspaces = useResource(() => materialsApi.workspaces(), [])

  const materials = useResource(
    () =>
      all
        ? fetchAll((limit, from) => materialsApi.list({ ...filters, limit, offset: from }))
        : materialsApi.list({ ...filters, limit: size, offset }),
    [applied, name, alias, family, category, scope, sort, size, offset, all]
  )

  async function removePicked() {
    setBusy(true)
    setFailure(null)
    setNotice(null)
    try {
      const done = await materialsApi.removeMany([...picked], {
        cascade,
        includeTestRuns: withRuns,
      })
      if (done.blocked.length > 0) {
        // **조용히 세지 않는다.** 막히는 이유가 셋이라(권한 · 시료가 남음 ·
        // 시험이 매달림) 개수만 말하면 무엇을 해야 하는지 알 수 없다.
        setFailure(
          new Error(
            `${done.deleted}건을 지웠습니다. 남은 것: ` +
              done.blocked.map((item) => `${item.name ?? item.id} (${item.reason})`).join(' · ')
          )
        )
      } else if (done.samples + done.specimens + done.test_runs > 0) {
        // **딸려 간 것을 말한다.** "2건 지웠습니다" 만 뜨면 사람은 시편 여섯이
        // 함께 사라진 것을 모른다.
        setNotice(
          `재료 ${done.deleted}건과 함께 시료 ${done.samples}건 · 시편 ` +
            `${done.specimens}건` +
            (done.test_runs > 0 ? ` · 시험 ${done.test_runs}건` : '') +
            `을 지웠습니다.`
        )
      }
      selection.clear()
      setRemoving(false)
      materials.reload()
      classes.reload()
    } catch (caught) {
      setFailure(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const page = materials.data
  const rows = page?.items ?? []
  // **Shift 로 범위를 고른다.** 한 쪽이 50건이라 하나씩 누르는 것은 일이 아니다.
  const selection = useRowSelection(rows.map((material) => material.id))
  const picked = selection.picked
  const total = page?.total ?? 0
  // 천장(2,000)에 걸렸는지. 걸렸으면 몇 건에서 멈췄는지 말한다.
  const truncated = all && rows.length < total

  return (
    <div>
      <PageHeader
        title="재료"
        description="규격 단위로 관리합니다. 실물 한 덩이는 시료, 잘라낸 조각은 시편입니다."
        actions={
          <>
            {/* **한 판에 열 몇 개를 넣는 것이 실제 작업이다.** 창을 열고 닫기를
                열 번 하면 그 자체가 일이 되고, 그러다 하나를 빠뜨린다. */}
            <Button variant="secondary" onClick={() => setBulk(true)}>
              <Plus className="size-4" />
              여러 개 등록
            </Button>
            <Button onClick={() => setRegistering(true)}>
              <Plus className="size-4" />
              재료 등록
            </Button>
          </>
        }
      />

      <form
        className="mb-4 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          setApplied(query.trim())
          // 검색은 결과 집합을 바꾼다. 3페이지에 머문 채로 좁히면 빈 화면이 뜬다.
          setOffset(0)
        }}
      >
        <div className="relative flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="이름 · 별칭 · Grade 로 찾기"
            className="pl-9"
          />
        </div>
        <Button type="submit" variant="secondary">
          찾기
        </Button>
      </form>

      {/* **분류 피커를 표 위에서 걷어냈다**(v1.128.0). 어느 상자가 어느 열을
          거르는지 글자로 적어 둬야 알 수 있었고(`Family`·`Category`), 열이 늘 때마다
          그 줄이 길어졌다. 열 머리에 붙으면 그 설명이 필요 없다 — 칸이 곧 그 열이다.

          위의 찾기 상자는 남긴다. 그건 **여러 열을 한꺼번에** 뒤지는 자리라
          열 하나에 매달 수 없다. */}

      <ErrorNotice error={materials.error} className="mb-4" />
      <ErrorNotice error={failure} className="mb-4" />
      {notice && <p className="mb-4 rounded-md border bg-muted/40 px-3 py-2 text-sm">{notice}</p>}

      {picked.size > 0 && (
        <div className="bg-muted/40 mb-3 flex flex-wrap items-center gap-3 rounded-md border px-3 py-2">
          <span className="text-sm">
            <b>{picked.size}건</b> 선택
          </span>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => {
              // **열 때마다 다시 센다.** 숫자는 서버가 낸다 — 화면이 나름대로
              // 세면 사람이 본 것과 실제로 지워지는 것이 어긋난다.
              setRemoving(true)
              setCascade(false)
              setWithRuns(false)
              setPlan(null)
              void materialsApi
                .bulkDeletePlan([...picked])
                .then(setPlan)
                .catch(() => setPlan(null))
            }}
          >
            <Trash2 className="size-3.5" />
            지우기
          </Button>
          <Button size="sm" variant="ghost" onClick={() => selection.clear()}>
            선택 해제
          </Button>
        </div>
      )}

      <ConfirmDialog
        open={removing}
        onClose={() => setRemoving(false)}
        title={`재료 ${picked.size}건을 지웁니다`}
        body={
          <>
            <p>
              고른 <b>{picked.size}건</b>이 목록에서 사라집니다.
              {!cascade && (
                <>
                  {' '}
                  <b>시료가 남아 있는 재료는 지워지지 않고</b> 이유와 함께 돌아옵니다.
                </>
              )}
            </p>
            <ul className="text-muted-foreground mt-2 max-h-24 space-y-0.5 overflow-y-auto font-mono text-xs">
              {rows
                .filter((material) => picked.has(material.id))
                .map((material) => (
                  <li key={material.id}>{material.record_name}</li>
                ))}
            </ul>

            {/* **아래까지 지우는 것은 켜야 한다.** 고르고 지우기를 누르는 것이
                갑자기 트리를 날리는 뜻이 되면 안 된다. */}
            <label className="mt-3 flex items-start gap-2 rounded-md border p-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={cascade}
                onChange={(event) => {
                  setCascade(event.target.checked)
                  if (!event.target.checked) setWithRuns(false)
                }}
              />
              <span>
                <span className="font-medium">아래까지 함께 지웁니다</span>
                <span className="text-muted-foreground mt-0.5 block text-xs">
                  {plan === null
                    ? '세는 중…'
                    : `시료 ${plan.samples}건 · 시편 ${plan.specimens}건` +
                      (plan.test_runs > 0 ? ` · 시험 ${plan.test_runs}건` : '')}
                </span>
              </span>
            </label>

            {/* 시료·시편은 이름표에 가깝지만 **시험은 잰 값이다.** 한 칸으로
                묶으면 「시료 정리하려다 측정 데이터를 날렸다」 가 난다. */}
            {cascade && plan !== null && plan.test_runs > 0 && (
              <label className="mt-2 flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={withRuns}
                  onChange={(event) => setWithRuns(event.target.checked)}
                />
                <span>
                  <span className="flex items-center gap-1.5 font-medium">
                    <TriangleAlert className="size-3.5" />
                    시험 {plan.test_runs}건도 함께 지웁니다
                  </span>
                  <span className="text-muted-foreground mt-0.5 block text-xs">
                    측정한 곡선과 처리 결과가 사라집니다. 안 켜면 시험을 문 재료만 이유와 함께
                    돌아옵니다.
                  </span>
                </span>
              </label>
            )}

            {plan !== null && plan.blocked.length > 0 && (
              <p className="mt-2 text-xs text-amber-700 dark:text-amber-500">
                {plan.blocked.length}건은 권한이 없어 지울 수 없습니다.
              </p>
            )}
          </>
        }
        confirmLabel="지우기"
        busy={busy}
        onConfirm={removePicked}
      />

      {!materials.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          <Boxes className="mx-auto mb-2 size-5 opacity-50" />
          {applied || family || category
            ? '조건에 맞는 재료가 없습니다. 검색어나 분류를 넓혀 보세요.'
            : '등록된 재료가 없습니다.'}
        </div>
      )}

      {rows.length > 0 && (
        <>
          <Table>
            <TableHeader>
              {/* **머리 띠를 본문과 가른다.** 거르는 칸이 들어가 두 층이 되면서
                  띠가 두꺼워졌는데, 배경이 없으면 첫 줄이 머리인지 자료인지
                  한눈에 안 갈린다. */}
              <TableRow className={FILTER_ROW}>
                {/* **20건을 하나씩 여는 것은 일이 아니다.** 골라서 한 번에 지운다. */}
                <TableHead className={`w-8 ${FILTER_HEAD}`}>
                  {/* 거르는 칸들과 **같은 높이에 선다.** 위에 붙으면 머리 띠에서
                      혼자 떠 보인다. */}
                  <div className="flex h-[3.25rem] items-end pb-2">
                    <input
                      type="checkbox"
                      aria-label="전부 선택"
                      checked={selection.allOn}
                      ref={(node) => {
                        if (node) node.indeterminate = selection.someOn
                      }}
                      onChange={(event) => selection.setAll(event.target.checked)}
                    />
                  </div>
                </TableHead>
                {/* **열마다 그 열을 거른다.** 서버가 거르므로 다음 쪽까지
                    걸러진다 — 화면에서 거르면 이 쪽에 실린 것만 걸러지고,
                    사람은 그것을 「없다」 로 읽는다. */}
                <TableHead className={`min-w-[11rem] ${FILTER_HEAD}`}>
                  <ColumnFilter
                    label="이름"
                    sort={handle('record_name')}
                    value={name}
                    onChange={(next) => {
                      setName(next)
                      setOffset(0)
                    }}
                    placeholder="SECC"
                  />
                </TableHead>
                <TableHead className={`min-w-[9rem] ${FILTER_HEAD}`}>
                  <ColumnFilter
                    label="별칭"
                    sort={handle('alias')}
                    value={alias}
                    onChange={(next) => {
                      setAlias(next)
                      setOffset(0)
                    }}
                  />
                </TableHead>
                {/* **분류를 두 열로 나눴다.** 한 칸에 `Metal / Steel` 로 붙어
                    있으면 거르는 칸도 하나여야 하는데, 둘은 따로 고르는 축이다
                    (Family 를 바꾸면 Category 후보가 달라진다). */}
                <TableHead className={`w-32 ${FILTER_HEAD}`}>
                  <ColumnFilter
                    label="Family"
                    sort={handle('family')}
                    value={family}
                    options={families}
                    onChange={(next) => {
                      setFamily(next)
                      // Family 를 바꾸면 이전 Category 가 그 안에 없을 수 있다.
                      // 남겨 두면 조용히 0건이 되고, 사람은 재료가 없는 줄 안다.
                      setCategory('')
                      setOffset(0)
                      selection.clear()
                    }}
                  />
                </TableHead>
                <TableHead className={`w-32 ${FILTER_HEAD}`}>
                  <ColumnFilter
                    label="Category"
                    sort={handle('category')}
                    value={category}
                    options={categories}
                    onChange={(next) => {
                      setCategory(next)
                      setOffset(0)
                    }}
                  />
                </TableHead>
                {/* 두께·시료 수는 **서버가 거르는 축이 아니다.** 거르는 칸을
                    두면 이 쪽에 실린 것만 걸러 거짓말을 한다. */}
                <TableHead className={`text-right ${FILTER_HEAD}`}>
                  <ColumnLabel align="right" sort={handle('spec_thickness')}>
                    두께
                  </ColumnLabel>
                </TableHead>
                <TableHead className={`text-right ${FILTER_HEAD}`}>
                  <ColumnLabel align="right">시료</ColumnLabel>
                </TableHead>
                <TableHead className={`w-36 ${FILTER_HEAD}`}>
                  {/* 서버가 거르는 축이 아니다 — 거르는 칸을 두면 이 쪽에 실린
                      것만 걸러 거짓말을 한다. */}
                  <ColumnLabel sort={handle('created_at')}>등록 일시</ColumnLabel>
                </TableHead>
                <TableHead className={`w-28 ${FILTER_HEAD}`}>
                  <ColumnFilter
                    label="소속"
                    value={scope}
                    options={[
                      { value: 'global', label: '전역' },
                      ...(workspaces.data ?? []).map((one) => ({
                        value: one.slug,
                        label: one.name,
                      })),
                    ]}
                    onChange={(next) => {
                      setScope(next)
                      setOffset(0)
                    }}
                  />
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((material) => (
                <TableRow key={material.id}>
                  <TableCell>
                    <input
                      type="checkbox"
                      aria-label={`${material.record_name} 선택`}
                      checked={picked.has(material.id)}
                      // **`onClick` 이다.** `onChange` 에는 shiftKey 가 안 실린다.
                      onClick={(event) => selection.toggle(material.id, event)}
                      onChange={() => {}}
                    />
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    <Link
                      to={`/materials/${material.id}`}
                      className="hover:text-primary hover:underline"
                    >
                      {material.record_name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{material.alias ?? '—'}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">{material.family}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {material.category}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {material.spec_thickness == null
                      ? '—'
                      : `${material.spec_thickness} ${material.spec_thickness_unit}`}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{material.sample_count}</TableCell>
                  <TableCell>
                    <Stamp at={material.created_at} />
                  </TableCell>
                  <TableCell>
                    {material.is_global ? (
                      <Badge variant="outline" className="gap-1">
                        <Globe2 className="size-3" />
                        전역
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground text-sm">
                        {material.owner_workspace_name ?? '—'}
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
            <span className="text-muted-foreground tabular-nums">
              {all ? `전체 ${rows.length}` : `${offset + 1}–${offset + rows.length}`} / {total}건
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
                  onClick={() => setOffset(Math.max(0, offset - size))}
                >
                  <ChevronLeft className="size-3.5" />
                  이전
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={offset + rows.length >= total}
                  onClick={() => setOffset(offset + size)}
                >
                  다음
                  <ChevronRight className="size-3.5" />
                </Button>
              </div>
            )}
          </div>

          {/* **조용히 자르지 않는다.** 천장에 걸렸으면 그 사실과 무엇을 하면
              되는지를 적는다. */}
          {truncated && (
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-500">
              {total}건 중 {rows.length}건까지만 한 번에 보여 줍니다 — 표가 그보다 길면 브라우저가
              버겁습니다. 검색으로 좁히세요.
            </p>
          )}
        </>
      )}

      <BulkMaterialDialog
        open={bulk}
        onClose={() => setBulk(false)}
        onDone={() => materials.reload()}
      />

      <NewMaterialDialog
        open={registering}
        onClose={() => setRegistering(false)}
        onDone={() => {
          setRegistering(false)
          materials.reload()
        }}
      />
    </div>
  )
}
