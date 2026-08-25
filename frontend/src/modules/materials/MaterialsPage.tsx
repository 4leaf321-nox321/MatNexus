/**
 * 재료 카탈로그 — 목록·검색·등록.
 *
 * 등록 폼에 **이름 미리보기**가 있다. 값을 넣는 동안 서버가 만들 이름을 그대로
 * 보여 주고, 이미 쓰이는 이름이면 저장 전에 알려 준다. 화면이 이름 규칙을 다시
 * 구현하지 않는 것이 핵심이다 — 기존 앱은 화면(DOM)이 ID를 만들어서 서버·배치가
 * 같은 이름을 만들 방법 자체가 없었다(ADR 0004).
 */

import { useState } from 'react'
import { Boxes, ChevronLeft, ChevronRight, Globe2, Plus, Search, X } from 'lucide-react'
import { Link } from 'react-router-dom'

import { materialsApi } from '@/modules/materials/api'
import { categoriesOf, familiesOf } from '@/modules/materials/classification'
import { BulkMaterialDialog } from '@/modules/materials/BulkMaterialDialog'
import { NewMaterialDialog } from '@/modules/materials/NewMaterialDialog'
import { fetchAll } from '@/shared/api/paging'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { OptionPicker } from '@/shared/components/OptionPicker'
import { PageHeader } from '@/shared/components/PageHeader'
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
  const all = size === 'all'

  // 무엇으로 거를 수 있는지는 **데이터가 정한다.** 목록에 실제로 있는 조합만 준다.
  const classes = useResource(() => materialsApi.classifications(), [])
  const rowsOf = classes.data ?? []
  // 세는 규칙은 옆패널과 **같은 것을 쓴다**(`classification.ts`).
  const families = familiesOf(rowsOf)
  const categories = categoriesOf(rowsOf, family)

  const materials = useResource(
    () =>
      all
        ? fetchAll((limit, from) =>
            materialsApi.list({ q: applied, family, category, limit, offset: from })
          )
        : materialsApi.list({ q: applied, family, category, limit: size, offset }),
    [applied, family, category, size, offset, all]
  )

  const page = materials.data
  const rows = page?.items ?? []
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

      {/* **분류는 눌러서 거른다.** 검색어에 'Metal' 을 치면 Grade·Details 에
          그 글자가 든 재료까지 걸린다 — 부분 일치라서 그렇다. 분류는 정확히
          일치로 좁혀야 "Metal 인 것만" 이 성립한다. */}
      {families.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <OptionPicker
            label="Family"
            value={family}
            options={families}
            onChange={(next) => {
              setFamily(next)
              // Family 를 바꾸면 이전 Category 가 그 안에 없을 수 있다. 남겨 두면
              // 조용히 0건이 되고, 사람은 재료가 없는 줄 안다.
              setCategory('')
              setOffset(0)
            }}
          />
          <OptionPicker
            label="Category"
            value={category}
            options={categories}
            onChange={(next) => {
              setCategory(next)
              setOffset(0)
            }}
          />
          {(family || category) && (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              onClick={() => {
                setFamily('')
                setCategory('')
                setOffset(0)
              }}
            >
              <X className="size-3.5" />
              필터 해제
            </Button>
          )}
        </div>
      )}

      <ErrorNotice error={materials.error} className="mb-4" />

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
              <TableRow>
                <TableHead>이름</TableHead>
                <TableHead>별칭</TableHead>
                <TableHead>분류</TableHead>
                <TableHead className="text-right">두께</TableHead>
                <TableHead className="text-right">시료</TableHead>
                <TableHead>소속</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((material) => (
                <TableRow key={material.id}>
                  <TableCell className="font-mono text-xs">
                    <Link
                      to={`/materials/${material.id}`}
                      className="hover:text-primary hover:underline"
                    >
                      {material.record_name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {material.alias ?? '—'}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {material.family} / {material.category}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {material.spec_thickness == null
                      ? '—'
                      : `${material.spec_thickness} ${material.spec_thickness_unit}`}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {material.sample_count}
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
              {total}건 중 {rows.length}건까지만 한 번에 보여 줍니다 — 표가 그보다 길면
              브라우저가 버겁습니다. 검색으로 좁히세요.
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
