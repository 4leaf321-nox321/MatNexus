/**
 * 문헌 물성 카탈로그 목록 — **우리가 실물을 갖지 않은 재료의 물성 저수지.**
 *
 * MaterialTwin 에서 이관한 42,209건(재료 2,663종)이다. 여기서는 보고 고르기만
 * 한다 — 값은 이관 스크립트로만 들어온다(ADR 0027).
 *
 * 정렬은 물성 많은 순 — 쓸 것이 많은 재료가 먼저다.
 */

import { Download, FileCode2, GitCompare, Grid3X3, ScatterChart } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { CATEGORY_LABELS, catalogApi } from '@/modules/catalog/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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
import { downloadFile } from '@/shared/api/client'
import { useResource } from '@/shared/hooks/useResource'

const STEP = 50
const MAX = 200

export default function CatalogPage() {
  // 재료 목록의 「문헌 물성 전부 보기」 가 검색어를 들고 들어온다.
  const [params] = useSearchParams()
  const initial = params.get('q') ?? ''
  const [typed, setTyped] = useState(initial)
  const [q, setQ] = useState(initial)
  // 커버리지 격자가 계통을 들고 들어온다 — '' 는 「미분류」다.
  const [subsystem, setSubsystem] = useState<string | undefined>(
    params.get('subsystem') ?? undefined
  )
  const [category, setCategory] = useState<string | undefined>()
  const [limit, setLimit] = useState(STEP)

  // 입력 250ms 뒤에 검색 — 한 글자마다 서버를 부르지 않는다.
  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(typed)
      setLimit(STEP)
    }, 250)
    return () => clearTimeout(timer)
  }, [typed])

  const summary = useResource(() => catalogApi.summary(), [])
  const page = useResource(
    () => catalogApi.materials({ q: q || undefined, subsystem, category, limit }),
    [q, subsystem, category, limit]
  )
  const [exporting, setExporting] = useState(false)

  /**
   * 지금 화면의 조건 그대로 파일을 받는다.
   *
   * **전부 받으면 70MB 가 넘는다**(값 4만여 건 · 조건과 근거가 값마다 붙는다).
   * 그래서 거른 채로 받는 길을 먼저 둔다 — 좁혀 놓고 누르면 그만큼만 온다.
   */
  async function exportJson() {
    setExporting(true)
    try {
      const query = new URLSearchParams()
      if (q) query.set('q', q)
      if (subsystem !== undefined) query.set('subsystem', subsystem)
      if (category) query.set('category', category)
      const suffix = query.toString() ? `?${query}` : ''
      await downloadFile(`/catalog/export${suffix}`, 'matnexus_catalog.json')
    } finally {
      setExporting(false)
    }
  }

  const rows = page.data?.items ?? []
  const total = page.data?.total ?? 0

  return (
    <div className="space-y-4">
      <PageHeader
        title="문헌 물성"
        description="문헌·데이터시트에서 채굴된 물성 카탈로그입니다. 모든 값에 출처와 품질 등급이 붙어 있고, 여기서는 값을 만들거나 고칠 수 없습니다."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" asChild>
              <Link to="/catalog/compare">
                <GitCompare className="size-4" />
                비교
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link to="/catalog/ashby">
                <ScatterChart className="size-4" />
                Ashby
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link to="/catalog/coverage">
                <Grid3X3 className="size-4" />
                커버리지
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link to="/catalog/deck">
                <FileCode2 className="size-4" />
                문헌 덱 생성
              </Link>
            </Button>
            {/* **지금 거른 것을 그대로 받는다.** 화면과 다른 것이 내려오면
                사람은 그 사실을 모른 채 그 파일로 계산한다. */}
            <Button variant="outline" onClick={() => void exportJson()} disabled={exporting}>
              <Download className="size-4" />
              {exporting ? '내보내는 중…' : 'JSON 내보내기'}
            </Button>
          </div>
        }
      />

      <ErrorNotice error={summary.error} />
      <ErrorNotice error={page.error} />

      {summary.data && (
        <p className="text-muted-foreground text-sm">
          재료 {summary.data.materials.toLocaleString('ko-KR')}종 · 물성값{' '}
          {summary.data.values.toLocaleString('ko-KR')}건 · 출처{' '}
          {summary.data.sources.toLocaleString('ko-KR')}건 · 물성 정의{' '}
          {summary.data.definitions.toLocaleString('ko-KR')}종
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Input
          aria-label="재료 이름 검색"
          placeholder="재료 이름으로 검색"
          className="max-w-sm"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
        />
        <select
          aria-label="부품 계통으로 필터"
          className="border-input bg-background h-9 rounded-md border px-2 text-sm"
          value={subsystem ?? '전체'}
          onChange={(event) => {
            const next = event.target.value
            setSubsystem(next === '전체' ? undefined : next)
            setLimit(STEP)
          }}
        >
          <option value="전체">계통 전체</option>
          {Object.entries(summary.data?.subsystems ?? {})
            .sort((a, b) => b[1] - a[1])
            .map(([key, count]) => (
              <option key={key || '_none'} value={key}>
                {key === '' ? '미분류' : key} ({count})
              </option>
            ))}
        </select>
        <select
          aria-label="재료 분류로 필터"
          className="border-input bg-background h-9 rounded-md border px-2 text-sm"
          value={category ?? '전체'}
          onChange={(event) => {
            const next = event.target.value
            setCategory(next === '전체' ? undefined : next)
            setLimit(STEP)
          }}
        >
          <option value="전체">분류 전체</option>
          {Object.entries(summary.data?.categories ?? {}).map(([key, count]) => (
            <option key={key} value={key}>
              {CATEGORY_LABELS[key] ?? key} ({count})
            </option>
          ))}
        </select>
      </div>

      {!page.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          조건에 맞는 재료가 없습니다.
        </div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>재료</TableHead>
                <TableHead>분류</TableHead>
                <TableHead>계통</TableHead>
                <TableHead>제조사</TableHead>
                <TableHead className="text-right">물성값</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((one) => (
                <TableRow key={one.id}>
                  <TableCell>
                    <Link className="text-sm font-medium hover:underline" to={`/catalog/${one.id}`}>
                      {one.name}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{CATEGORY_LABELS[one.category] ?? one.category}</Badge>
                  </TableCell>
                  <TableCell>
                    {one.subsystem ?? '미분류'}
                  </TableCell>
                  <TableCell className="max-w-64 truncate">
                    {one.manufacturer ?? '—'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {one.value_count}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {rows.length > 0 && rows.length < total && (
        <div className="flex items-center gap-3">
          {limit < MAX ? (
            <Button variant="outline" onClick={() => setLimit((now) => Math.min(now + STEP, MAX))}>
              더 보기 ({rows.length}/{total.toLocaleString('ko-KR')})
            </Button>
          ) : (
            <p className="text-muted-foreground text-xs">
              {total.toLocaleString('ko-KR')}종 중 {rows.length}종까지만 보여 줍니다 — 검색이나
              계통으로 좁혀 주세요.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
