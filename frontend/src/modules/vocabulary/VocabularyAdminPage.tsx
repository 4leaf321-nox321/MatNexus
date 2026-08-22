/**
 * 기준정보 관리 — **잘못 들어간 값을 고칠 자리.**
 *
 * 기준정보를 켜 두고 관리 화면이 없으면 절반만 한 것이다. `'???'` 같은 값이
 * 들어갔을 때(실제로 개발 DB 에 있다) 고칠 데가 없고, 안 쓰는 값이 피커에
 * 계속 뜬다.
 *
 * ## 지우는 버튼이 없다
 *
 * 값을 지우면 그것을 가리키던 시료가 어느 제조사였는지 알 수 없게 된다. 그건
 * 오타를 고치는 것과 전혀 다른 일이다. 대신 **감추기**(`deprecated`)를 둔다 —
 * 피커에서만 사라지고 이미 가리키는 것은 그대로다.
 *
 * ## 이름을 고치면 가리키던 것이 전부 따라온다
 *
 * 외래키라서 그렇다(ADR 0010). 문자열이었으면 시료 수천 건을 훑어야 했다.
 * 그래서 이 화면의 '이름 고치기' 는 가벼운 조작처럼 보이지만 **파급이 크다** —
 * 몇 건이 따라오는지 옆에 적어 둔다.
 */

import { useEffect, useState } from 'react'
import {
  Eye,
  EyeOff,
  GitMerge,
  Pencil,
  Plus,
  RefreshCw,
  Ruler,
  ShieldCheck,
  Tag,
  Trash2,
  X,
} from 'lucide-react'

import { BULK_MAX, vocabularyApi } from '@/modules/vocabulary/api'
import { SpecimenFieldsDialog } from '@/modules/vocabulary/SpecimenFieldsDialog'
import { SpecimenStandardDialog } from '@/modules/vocabulary/SpecimenStandardDialog'
import { VocabularyField } from '@/modules/vocabulary/VocabularyField'
import type {
  BulkResult,
  DeleteResult,
  DriftReport,
  Term,
  Vocabulary,
} from '@/modules/vocabulary/api'
import { ApiError } from '@/shared/api/client'
import { fetchAll } from '@/shared/api/paging'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Textarea } from '@/shared/components/ui/textarea'
import { Label } from '@/shared/components/ui/label'
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
 * 이 축이 치수와 어떤 관계인가. **축 목록에서 알아낸다.**
 *
 *   `standard`  값이 치수를 갖는다(`attribute_source === 'parent'`)
 *   `category`  값이 **기본 칸**을 갖는다 — 위 축의 부모다
 *
 * 화면에 `slug === 'specimen_standard'` 를 적으면 축이 하나 더 생길 때 두 곳을
 * 고쳐야 하고, 그러면 한 곳을 빠뜨린다.
 */
export type AxisRole = 'standard' | 'category' | null

export function roleOf(axis: Vocabulary, axes: Vocabulary[]): AxisRole {
  if (axis.attribute_source === 'parent') return 'standard'
  const child = axes.some(
    (item) => item.parent_slug === axis.slug && item.attribute_source === 'parent'
  )
  return child ? 'category' : null
}

export default function VocabularyAdminPage() {
  const vocabularies = useResource(() => vocabularyApi.list(), [])
  const [slug, setSlug] = useState<string | null>(null)
  const axes = vocabularies.data ?? []
  const active = axes.find((item) => item.slug === slug) ?? axes[0] ?? null


  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="기준정보"
        description="제조사·강종 같은 값의 목록. 오타를 고치고, 안 쓰는 값을 감춥니다."
      />

      <ErrorNotice error={vocabularies.error} className="mb-4" />

      <div className="mb-4 flex flex-wrap gap-2">
        {axes.map((item) => (
          <Button
            key={item.slug}
            size="sm"
            variant={active?.slug === item.slug ? 'default' : 'outline'}
            onClick={() => setSlug(item.slug)}
          >
            {item.label}
            <span className="ml-1 opacity-60">{item.term_count}</span>
          </Button>
        ))}
      </div>

      {active && <TermTable vocabulary={active} role={roleOf(active, axes)} />}

      <DriftPanel onRepaired={() => vocabularies.reload()} />
    </div>
  )
}

/**
 * 어긋남 점검 — **문자열과 기준정보가 같은 말을 하는가.**
 *
 * 지금은 같은 사실을 두 벌로 들고 있다(ADR 0010 Expand). `materials.family`
 * 문자열과 `family_term_id` 다. 쓰는 경로는 하나지만 그 밖으로 새는 길이 있으면
 * 조용히 벌어진다 — **조용한 것이 문제다.** 개발 DB 에서 2건이 벌어진 채로
 * 있었고, 이 점검을 만들고 나서야 알았다. 그 2건이 결함 하나를 드러냈다: 기준정보
 * 이름을 고치면 재료·시료·시편·시험 이름 넷은 따라 바뀌는데 **정작 그 값 자신은
 * 옛 표기 그대로**였고 API 는 200 을 냈다.
 *
 * 접어 둔다. 평소에는 0 이고, 0 인 것을 매번 크게 보여 줄 이유가 없다.
 */
function DriftPanel({ onRepaired }: { onRepaired: () => void }) {
  const [open, setOpen] = useState(false)
  const [report, setReport] = useState<DriftReport | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function run(fix: boolean) {
    setBusy(true)
    setError(null)
    try {
      setReport(fix ? await vocabularyApi.repair() : await vocabularyApi.measureDrift())
      if (fix) onRepaired()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('점검하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  // **열 때는 기록을 읽기만 한다.** 창을 열 때마다 새로 재면 이력이 사람이
  // 창을 연 횟수가 되고, 게이트가 묻는 "저절로 돌 때도 계속 0 이었나" 에 답할
  // 수 없게 된다.
  async function load() {
    setBusy(true)
    setError(null)
    try {
      setReport(await vocabularyApi.drift())
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('점검 기록을 읽지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        className="text-muted-foreground hover:text-foreground mt-6 text-xs underline"
        onClick={() => {
          setOpen(true)
          void load()
        }}
      >
        어긋남 점검
      </button>
    )
  }

  return (
    <section className="mt-6 rounded-md border p-3">
      <div className="mb-2 flex items-center gap-2">
        <ShieldCheck className="size-4" />
        <p className="text-sm font-medium">어긋남 점검</p>
        {report?.checked_at && (
          <span className="text-muted-foreground text-xs">
            마지막 {new Date(report.checked_at).toLocaleString('ko-KR')}
          </span>
        )}
        <Button
          size="sm"
          variant="outline"
          className="ml-auto h-7 text-xs"
          disabled={busy}
          onClick={() => void run(false)}
        >
          다시 재기
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 text-xs"
          onClick={() => setOpen(false)}
        >
          접기
        </Button>
      </div>

      <ErrorNotice error={error} className="mb-2" />

      <p className="text-muted-foreground mb-2 text-xs">
        값을 두 벌로 들고 있는 동안(문자열과 기준정보) 둘이 벌어질 수 있습니다. 문자열
        쪽을 지우기 전에 이 수가 <strong>한 릴리스 동안</strong> 0 이어야 합니다.
        워커가 6시간마다 스스로 재고, 벌어지면 로그에 남깁니다.
      </p>

      {report && report.total === 0 && (
        <div className="text-xs">
          <p>어긋난 곳이 없습니다.</p>
          {/* **"지금 0" 이 아니라 "언제부터 0" 이 답이다.** 문자열 컬럼을 지우는
              조건이 "한 릴리스 동안 0" 이라, 한 번 눌러서 0 인 것으로는 부족하다.
              워커가 6시간마다 스스로 재고 여기 쌓인다. */}
          {report.clean_since && (
            <p className="text-muted-foreground mt-0.5">
              {new Date(report.clean_since).toLocaleString('ko-KR')} 부터 {report.clean_checks}회
              연속 0 입니다.
            </p>
          )}
        </div>
      )}

      {report && report.total > 0 && (
        <div className="space-y-2">
          <p className="text-destructive text-xs font-medium">{report.total}건이 벌어졌습니다.</p>
          {report.items.map((item) => (
            <div key={`${item.table}.${item.field}`} className="text-xs">
              <p className="font-mono">
                {item.table}.{item.field}{' '}
                <span className="text-muted-foreground">({item.label})</span> {item.count}건
              </p>
              {item.examples.map((example) => (
                <p key={example} className="text-muted-foreground ml-3 font-mono">
                  {example}
                </p>
              ))}
            </div>
          ))}
          {/* **기준정보가 정본이다.** 문자열은 Contract 전까지의 캐시이고, 캐시가
              틀렸으면 원본에서 다시 만드는 것이 유일한 방향이다. 다만 안 이어진
              행은 반대로 문자열을 기준정보로 올린다 — 지우면 그 재료가 무엇이었는지
              사라진다. */}
          <Button size="sm" className="h-7 text-xs" disabled={busy} onClick={() => void run(true)}>
            기준정보에 맞춰 고치기
          </Button>
        </div>
      )}
    </section>
  )
}

//: 한 쪽에 몇 개. `ALL` 은 상한(2,000)까지 긁어 온다 — 20만 개를 브라우저로
//: 보낼 수는 없으므로 걸리면 화면이 말한다.
const ALL = -1
const PAGE_SIZES = [50, 100, ALL] as const

function TermTable({ vocabulary, role }: { vocabulary: Vocabulary; role: AxisRole }) {
  /** 규격 축이면 치수를, 분류 축이면 기본 칸을 다룬다. */
  const hasAttributes = role !== null
  const [term, setTerm] = useState('')
  const [showHidden, setShowHidden] = useState(false)
  const [leastUsed, setLeastUsed] = useState(false)
  const [editing, setEditing] = useState<Term | null>(null)
  const [sizing, setSizing] = useState<Term | null>(null)
  const [detail, setDetail] = useState<Term | null>(null)
  const [showCandidates, setShowCandidates] = useState(false)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [size, setSize] = useState<number>(PAGE_SIZES[0])
  const [offset, setOffset] = useState(0)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [removed, setRemoved] = useState<DeleteResult | null>(null)

  // 검색은 서버가 한다 — 기준정보가 수만 개가 되면 전체를 받을 수 없다.
  const terms = useResource(
    () =>
      size === ALL
        ? // **'전체' 는 상한이 있다.** 20만 개를 브라우저로 보낼 수는 없다 —
          // 걸리면 아래에서 몇 건에서 멈췄는지 말한다.
          fetchAll((limit, from) =>
            vocabularyApi.search(vocabulary.slug, term, {
              includeHidden: showHidden,
              leastUsed,
              limit,
              offset: from,
            })
          )
        : vocabularyApi.search(vocabulary.slug, term, {
            includeHidden: showHidden,
            leastUsed,
            limit: size,
            offset,
          }),
    [vocabulary.slug, term, showHidden, leastUsed, size, offset]
  )

  // 검색·필터가 바뀌면 첫 쪽으로. 안 그러면 3쪽에서 검색해 0건이 뜬다.
  useEffect(() => {
    setOffset(0)
    setPicked(new Set())
  }, [vocabulary.slug, term, showHidden, leastUsed, size])

  async function removeSelected() {
    setError(null)
    setRemoved(null)
    try {
      const result = await vocabularyApi.removeMany(vocabulary.slug, [...picked])
      setRemoved(result)
      setPicked(new Set())
      terms.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
    }
  }

  function togglePick(id: string) {
    setPicked((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function recount() {
    setError(null)
    try {
      await vocabularyApi.recount(vocabulary.slug)
      terms.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('다시 세지 못했습니다.'))
    }
  }

  async function toggle(item: Term, next: 'active' | 'deprecated') {
    setError(null)
    try {
      await vocabularyApi.update(vocabulary.slug, item.id, { status: next })
      terms.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('바꾸지 못했습니다.'))
    }
  }

  const page = terms.data
  const rows = page?.items ?? []
  const total = page?.total ?? 0
  // 천장에 걸렸는지. 걸렸으면 몇 건에서 멈췄는지 말한다.
  const truncated = size === ALL && rows.length < total

  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <Input
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder={`${vocabulary.label} 찾기`}
          className="h-8 max-w-xs text-sm"
        />
        <Badge variant="outline" className="text-xs">
          {vocabulary.entry_policy === 'open' ? '사용자가 추가할 수 있음' : '관리자만 추가'}
        </Badge>
        {/* **오타는 늘 `쓰는 곳 1` 로 생긴다.** 기본 정렬(많이 쓰는 순)에서는
            목록 끝에 묻히므로, 뒤집으면 검토할 것이 맨 위로 온다. 입력을 앞에서
            막는 대신 뒤에서 보이게 하는 장치다. */}
        <Button
          size="sm"
          variant={leastUsed ? 'default' : 'outline'}
          className="h-8 text-xs"
          title="새로 생긴 오타를 찾을 때"
          onClick={() => setLeastUsed((value) => !value)}
        >
          적게 쓰이는 것부터
        </Button>
        {/* **되돌릴 길이 없으면 감추기도 막다른 길이다.** */}
        <Button
          size="sm"
          variant={showHidden ? 'default' : 'outline'}
          className="h-8 text-xs"
          onClick={() => setShowHidden((value) => !value)}
        >
          감춘 값도 보기
        </Button>
        {/* **미리 갖춰 놓을 수 있어야 한다.** 지금까지 값은 누가 폼에서 써야만
            생겼고, 그러면 첫 사람이 무엇을 칠지에 목록이 끌려간다. */}
        <Button size="sm" className="ml-auto h-8 text-xs" onClick={() => setAdding(true)}>
          <Plus className="size-3.5" />
          값 추가
        </Button>
        <Button
          size="sm"
          variant={showCandidates ? 'default' : 'outline'}
          className="h-8 text-xs"
          title="구두점·공백까지 지운 키로 묶어 봅니다"
          onClick={() => setShowCandidates((value) => !value)}
        >
          <GitMerge className="size-3.5" />
          합칠 만한 값
        </Button>
        {/* **성능 때문에 둔 캐시라면 틀렸을 때 고치는 버튼이 있어야 한다.** */}
        <Button
          size="sm"
          variant="outline"
          className="h-8 text-xs"
          title="'쓰는 곳' 숫자를 다시 셉니다"
          onClick={() => void recount()}
        >
          <RefreshCw className="size-3.5" />
          다시 세기
        </Button>
      </div>

      <ErrorNotice error={terms.error ?? error} className="mb-3" />

      {adding && (
        <AddTermDialog
          vocabulary={vocabulary}
          onClose={() => setAdding(false)}
          onAdded={() => terms.reload()}
        />
      )}

      {/* **분류에서는 칸을, 규격에서는 값을 고친다.** 분류의 값에 치수를
          적을 자리는 없다 — 치수는 규격이 갖는다. */}
      {sizing && role === 'category' && (
        <SpecimenFieldsDialog
          slug={vocabulary.slug}
          term={sizing}
          onClose={() => setSizing(null)}
          onSaved={() => {
            setSizing(null)
            terms.reload()
          }}
        />
      )}

      {sizing && role === 'standard' && (
        <SpecimenStandardDialog
          slug={vocabulary.slug}
          term={sizing}
          onClose={() => setSizing(null)}
          onSaved={() => {
            setSizing(null)
            terms.reload()
          }}
        />
      )}

      {detail && (
        <TermDetailDialog
          slug={vocabulary.slug}
          parentSlug={vocabulary.parent_slug ?? null}
          term={detail}
          onClose={() => setDetail(null)}
          onChanged={() => terms.reload()}
        />
      )}

      {editing && (
        <RenameDialog
          slug={vocabulary.slug}
          term={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            terms.reload()
          }}
        />
      )}

      {/* **고른 것이 몇 개인지 늘 보여야 한다.** 여러 쪽을 오가며 고르면 지금
          몇 개를 들고 있는지 잊는다. */}
      {picked.size > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border p-2.5">
          <span className="text-sm">
            <b>{picked.size}개</b> 골랐습니다
          </span>
          <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>
            선택 해제
          </Button>
          <Button
            size="sm"
            variant="destructive"
            className="ml-auto"
            onClick={() => void removeSelected()}
          >
            <Trash2 className="size-3.5" />
            지우기
          </Button>
        </div>
      )}

      {removed && (
        <div className="mb-3 rounded-md border p-2.5 text-sm">
          <p>
            지움 <b>{removed.deleted}</b>
            {removed.blocked > 0 && (
              <span className="text-amber-700 dark:text-amber-500">
                {' '}
                · 못 지움 {removed.blocked}
              </span>
            )}
          </p>
          {/* **무엇이 막는지 말한다.** "지울 수 없습니다" 만 주면 사람은 왜인지
              알아내려고 목록을 뒤진다. */}
          {removed.items.some((item) => !item.deleted) && (
            <ul className="text-muted-foreground mt-1 space-y-0.5 text-xs">
              {removed.items
                .filter((item) => !item.deleted)
                .map((item) => (
                  <li key={item.id}>
                    <b>{item.value}</b> — {item.reason}
                  </li>
                ))}
            </ul>
          )}
        </div>
      )}

      {showCandidates ? (
        <MergeCandidates slug={vocabulary.slug} onChanged={() => terms.reload()} />
      ) : (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              {/* **한 번에 고르기.** 이 쪽에 보이는 것만 고른다 — 안 보이는
                  것까지 고르면 무엇을 지우는지 모르는 채로 누르게 된다. */}
              <input
                type="checkbox"
                aria-label="이 쪽 전체 선택"
                checked={rows.length > 0 && rows.every((item) => picked.has(item.id))}
                onChange={(event) =>
                  setPicked((current) => {
                    const next = new Set(current)
                    for (const item of rows) {
                      if (event.target.checked) next.add(item.id)
                      else next.delete(item.id)
                    }
                    return next
                  })
                }
              />
            </TableHead>
            <TableHead>값</TableHead>
            {/* **치수와 관계있는 축에서만 뜬다.** 제조사에 '치수' 칸이 있으면
                그것이 무엇을 뜻하는지 아무도 모른다. */}
            {hasAttributes && (
              <TableHead>{role === 'category' ? '기본 칸' : '치수'}</TableHead>
            )}
            <TableHead>상위</TableHead>
            <TableHead className="text-right">쓰는 곳</TableHead>
            <TableHead className="w-40" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((item) => (
            <TableRow key={item.id} className={item.status === 'deprecated' ? 'opacity-50' : ''}>
              <TableCell>
                <input
                  type="checkbox"
                  aria-label={`${item.value} 선택`}
                  checked={picked.has(item.id)}
                  onChange={() => togglePick(item.id)}
                />
              </TableCell>
              <TableCell>
                {item.value}
                {item.status === 'deprecated' && (
                  <Badge variant="outline" className="ml-2 text-xs">
                    감춤
                  </Badge>
                )}
              </TableCell>
              {hasAttributes && (
                <TableCell className="text-sm">
                  {role === 'category' ? (
                    /* **칸이 0 이면 그 분류의 규격은 치수를 하나도 못 갖는다.** */
                    item.field_count > 0 ? (
                      `${item.field_count}개`
                    ) : (
                      <span className="text-destructive">칸 없음</span>
                    )
                  ) : (
                    <>
                      {/* 치수가 비어 있으면 **그 사실을 말한다.** 규격 이름만
                          있는 값은 시편 치수를 아무것도 못 채워 준다. */}
                      {Object.keys(item.attributes ?? {}).length > 0 ? (
                        `치수 ${Object.keys(item.attributes).length}개`
                      ) : (
                        <span className="text-destructive">치수 없음</span>
                      )}
                      {(item.extra_fields ?? []).length > 0 && (
                        <span className="text-muted-foreground ml-1.5 text-xs">
                          · 이 규격 칸 {item.extra_fields.length}개
                        </span>
                      )}
                    </>
                  )}
                </TableCell>
              )}
              <TableCell className="text-muted-foreground text-sm">
                {item.parent_value ?? '—'}
              </TableCell>
              {/* **몇 건이 따라오는지 보여 준다.** 이름 고치기가 가벼운 조작처럼
                  보이지만 외래키라 이 수만큼이 함께 바뀐다. */}
              <TableCell className="text-right tabular-nums">{item.usage_count}</TableCell>
              <TableCell className="text-right">
                {hasAttributes && (
                  <Button
                    size="sm"
                    variant="ghost"
                    title={
                      role === 'category'
                        ? '기본 칸 — 이 분류의 규격 전부가 갖는 치수'
                        : '치수 — 이 규격이 정하는 값'
                    }
                    aria-label={`${item.value} ${role === 'category' ? '기본 칸' : '치수'}`}
                    onClick={() => setSizing(item)}
                  >
                    <Ruler className="size-3.5" />
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  title="표기·상위 분류"
                  onClick={() => setDetail(item)}
                >
                  <Tag className="size-3.5" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  title="이름 고치기 — 가리키던 것이 전부 따라옵니다"
                  onClick={() => setEditing(item)}
                >
                  <Pencil className="size-3.5" />
                </Button>
                {/* 지우기가 아니라 감추기다. 지우면 그것을 가리키던 시료가
                    무엇이었는지 알 수 없게 된다. */}
                {item.status === 'deprecated' ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    title="다시 피커에 보이게"
                    onClick={() => void toggle(item, 'active')}
                  >
                    <Eye className="size-3.5" />
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    title="피커에서 감추기 — 이미 쓰는 곳은 그대로입니다"
                    onClick={() => void toggle(item, 'deprecated')}
                  >
                    <EyeOff className="size-3.5" />
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      )}

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="text-muted-foreground">
          {size === ALL
            ? `${rows.length.toLocaleString('ko-KR')}건`
            : `${total.toLocaleString('ko-KR')}건 중 ${offset + 1}–${Math.min(offset + size, total)}`}
        </span>

        <div className="flex gap-1">
          {PAGE_SIZES.map((option) => (
            <Button
              key={option}
              size="sm"
              variant={size === option ? 'default' : 'outline'}
              className="h-7 text-xs"
              onClick={() => setSize(option)}
            >
              {option === ALL ? '전체' : option}
            </Button>
          ))}
        </div>

        {size !== ALL && (
          <div className="ml-auto flex gap-1">
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - size))}
            >
              이전
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              disabled={offset + size >= total}
              onClick={() => setOffset(offset + size)}
            >
              다음
            </Button>
          </div>
        )}
      </div>

      {/* **조용히 자르지 않는다.** 천장에 걸렸으면 몇 건에서 멈췄는지 말한다. */}
      {truncated && (
        <p className="mt-2 text-xs text-amber-700 dark:text-amber-500">
          {rows.length.toLocaleString('ko-KR')}건까지만 불러왔습니다 (전체{' '}
          {total.toLocaleString('ko-KR')}건). 검색으로 좁히세요.
        </p>
      )}

      {!showCandidates && !terms.loading && rows.length === 0 && (
        <p className="text-muted-foreground py-10 text-center text-sm">
          {term ? `'${term}' 에 맞는 값이 없습니다.` : '아직 값이 없습니다.'}
        </p>
      )}

      <p className="text-muted-foreground mt-4 text-xs">
        감춘 값은 피커에서만 사라집니다 — <b>이미 그 값을 쓰는 시료는 그대로</b>입니다.
        지우는 길은 두지 않았습니다. 지우면 그 시료가 무엇이었는지 알 수 없게 됩니다.
      </p>
    </section>
  )
}

/**
 * 축마다 이름 변경의 파급이 다르다.
 *
 * 대부분은 그 값을 가리키던 행의 표시가 바뀔 뿐이다. **강종은 다르다** — 강종은
 * 재료 이름을 만들므로(ADR 0004) 재료·시료·시편·시험 이름이 전부 다시 만들어진다.
 * "쓰는 곳 N곳" 으로는 그 파급을 말할 수 없다.
 */
const RENAME_IMPACT: Record<string, string> = {
  grade: '이 강종을 쓰는 재료 이름이 바뀌고, 그 아래 시료·시편·시험 이름도 전부 따라 바뀝니다.',
}

function RenameDialog({
  slug,
  term,
  onClose,
  onSaved,
}: {
  slug: string
  term: Term
  onClose: () => void
  onSaved: () => void
}) {
  const [value, setValue] = useState(term.value)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  async function submit() {
    setBusy(true)
    setFailure(null)
    try {
      await vocabularyApi.update(slug, term.id, { value })
      onSaved()
    } catch (error) {
      // 같은 이름이 이미 있으면 서버가 409 와 함께 "병합을 쓰세요" 를 준다 —
      // 말없이 합치지 않는다.
      setFailure(error instanceof ApiError ? error.message : '고치지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>이름 고치기</DialogTitle>
          <DialogDescription>
            이 값을 쓰는 <b>{term.usage_count}곳</b>이 함께 바뀝니다.
            {RENAME_IMPACT[slug] && (
              <span className="mt-1 block text-amber-700 dark:text-amber-500">
                {RENAME_IMPACT[slug]}
              </span>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label htmlFor="term-value">값</Label>
          <Input
            id="term-value"
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </div>

        {failure && <p className="text-destructive text-sm">{failure}</p>}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={submit} disabled={busy || value.trim() === ''}>
            고치기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * 값 하나를 들여다보는 창 — **표기·부모·합치기.**
 *
 * 셋을 한 창에 두는 이유: 다 같은 질문의 다른 답이다. `'포스코(주)'` 를 만났을 때
 * 할 수 있는 일은 셋뿐이다 — 별칭으로 잇거나, 부모를 정하거나, 다른 값에 합치거나.
 * 화면을 나누면 무엇을 골라야 하는지가 흐려진다.
 */
function TermDetailDialog({
  slug,
  parentSlug,
  term,
  onClose,
  onChanged,
}: {
  slug: string
  parentSlug: string | null
  term: Term
  onClose: () => void
  onChanged: () => void
}) {
  const [alias, setAlias] = useState('')
  const [parent, setParent] = useState(term.parent_value ?? '')
  const [failure, setFailure] = useState<string | null>(null)
  const aliases = useResource(() => vocabularyApi.aliases(slug, term.id), [slug, term.id])

  async function guarded(action: () => Promise<unknown>) {
    setFailure(null)
    try {
      await action()
      aliases.reload()
      onChanged()
    } catch (error) {
      setFailure(error instanceof ApiError ? error.message : '실패했습니다.')
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{term.value}</DialogTitle>
          <DialogDescription>쓰는 곳 {term.usage_count}곳</DialogDescription>
        </DialogHeader>

        {parentSlug && (
          <div className="space-y-1.5">
            <div className="flex items-end gap-2">
              {/* **있는 것 중에서 고른다.** 자유 입력이면 오타를 서버가 422 로
                  거절할 뿐이고, 어떤 값이 있는지 보이지도 않는다.
                  새로 만들지는 못하게 둔다 — 여기는 정리하는 자리다. */}
              <div className="flex-1">
                <VocabularyField
                  slug={parentSlug}
                  label="상위 분류"
                  value={parent}
                  allowCreate={false}
                  onChange={setParent}
                />
              </div>
              <Button
                variant="outline"
                onClick={() =>
                  void guarded(() =>
                    vocabularyApi.update(slug, term.id, { parent_value: parent })
                  )
                }
              >
                저장
              </Button>
            </div>
            {/* 백필이 못 이은 값(부모가 갈렸던 것)을 사람이 정하는 자리다. */}
            <p className="text-muted-foreground text-xs">
              고른 값 아래로 들어갑니다. <b>'고르지 않음'</b> 을 고르면 부모를 뗍니다 —
              좁히기가 안 될 뿐, 값은 그대로 씁니다.
            </p>
          </div>
        )}

        <div className="space-y-1.5">
          <Label htmlFor="term-alias">다른 표기</Label>
          <div className="flex gap-2">
            <Input
              id="term-alias"
              value={alias}
              placeholder="POSCO / 포스코(주) …"
              onChange={(event) => setAlias(event.target.value)}
            />
            <Button
              variant="outline"
              disabled={alias.trim() === ''}
              onClick={() =>
                void guarded(async () => {
                  await vocabularyApi.addAlias(slug, term.id, alias)
                  setAlias('')
                })
              }
            >
              잇기
            </Button>
          </div>
          {/* **예방이다.** 등록해 두면 값을 만들 때 게이트가 여기까지 뒤져서
              애초에 중복이 안 생긴다 — 사후에 합치는 것보다 싸다. */}
          <p className="text-muted-foreground text-xs">
            이 표기로 입력하면 <b>새 값이 안 생기고</b> 이 값이 선택됩니다.
          </p>
          <ul className="space-y-1">
            {(aliases.data ?? []).map((item) => (
              <li key={item.id} className="flex items-center gap-2 text-sm">
                <span>{item.alias}</span>
                <button
                  type="button"
                  className="text-muted-foreground hover:text-destructive"
                  onClick={() =>
                    void guarded(() =>
                      vocabularyApi.removeAlias(slug, term.id, item.id)
                    )
                  }
                >
                  <X className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
        </div>

        {failure && <p className="text-destructive text-sm">{failure}</p>}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            닫기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * 합칠 만한 값 묶음.
 *
 * 구두점·공백까지 지운 키로 묶으므로 오탐이 뜬다 — `'포스코'` 와 `'포스코특수강'`
 * 은 다른 회사다. 그래서 **합치는 것은 사람이 누르고**, 아니라고 판정한 쌍은
 * 기억한다. 안 기억하면 같은 것을 매번 다시 묻게 되고 목록을 아무도 안 본다.
 */
function MergeCandidates({
  slug,
  onChanged,
}: {
  slug: string
  onChanged: () => void
}) {
  const groups = useResource(() => vocabularyApi.mergeCandidates(slug), [slug])
  const [error, setError] = useState<Error | null>(null)
  const found = groups.data ?? []

  async function guarded(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
      groups.reload()
      onChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('실패했습니다.'))
    }
  }

  if (!groups.loading && found.length === 0) {
    return (
      <p className="text-muted-foreground py-6 text-center text-sm">
        합칠 만한 값이 없습니다.
      </p>
    )
  }

  return (
    <div className="space-y-2">
      <ErrorNotice error={groups.error ?? error} />
      {found.map((group) => {
        // 많이 쓰이는 것이 앞이다 — 그것을 생존값으로 추천한다.
        const [survivor, ...rest] = group
        return (
          <div key={survivor.id} className="rounded-md border p-3">
            <p className="text-sm">
              <b>{survivor.value}</b>
              <span className="text-muted-foreground"> ({survivor.usage_count})</span>
              {rest.map((item) => (
                <span key={item.id} className="text-muted-foreground">
                  {' · '}
                  {item.value} ({item.usage_count})
                </span>
              ))}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {rest.map((item) => (
                <Button
                  key={item.id}
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    void guarded(() =>
                      vocabularyApi.merge(slug, item.id, survivor.id)
                    )
                  }
                >
                  '{item.value}' 를 '{survivor.value}' 로 합치기
                </Button>
              ))}
              <Button
                size="sm"
                variant="ghost"
                title="다시 묻지 않습니다"
                onClick={() =>
                  void guarded(async () => {
                    for (const item of rest) {
                      await vocabularyApi.dismiss(slug, survivor.id, item.id)
                    }
                  })
                }
              >
                다른 값입니다
              </Button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

/**
 * 값 추가 — **관리자가 목록을 미리 갖춰 놓는 자리.**
 *
 * 지금까지 값은 누군가 폼에서 써야만 생겼다. 그러면 제조사 목록을 먼저 정리해
 * 두고 싶어도 방법이 없고, 첫 사람이 무엇을 칠지에 목록이 끌려간다.
 *
 * ## 이미 있는 값을 쳤을 때
 *
 * 서버는 **정규 값을 돌려준다**(409 가 아니다). 그래서 '포스코(주)' 를 더하려
 * 했는데 그것이 '포스코' 의 별칭이면 '포스코' 가 온다. 화면이 그 사실을 말하지
 * 않으면 사람은 자기가 친 값이 추가된 줄 안다 — 목록에 없으니 다시 치게 된다.
 */
//: 붙여 넣기 예시. 부모가 있는 축이면 **줄마다 상위를 적을 수 있다**는 것을
//: 보여 주는 것이 요점이다 — 도움말만으로는 아무도 안 읽는다.
const PLACEHOLDER = {
  plain: '한 줄에 하나씩\n포스코\n현대제철',
  child: '한 줄에 하나씩\nSECC\n\n상위가 다르면\nSteel > DP590\nPP > PP-GF30',
} as const

function AddTermDialog({
  vocabulary,
  onClose,
  onAdded,
}: {
  vocabulary: Vocabulary
  onClose: () => void
  onAdded: () => void
}) {
  const [mode, setMode] = useState<'one' | 'many'>('one')
  const [value, setValue] = useState('')
  const [lines, setLines] = useState('')
  const [parent, setParent] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [resolved, setResolved] = useState<{ typed: string; got: string } | null>(null)
  const [bulk, setBulk] = useState<BulkResult | null>(null)

  async function submitMany() {
    // 상한을 넘으면 서버가 422 를 준다 — 여기서 미리 자르면 **몇 줄이 빠졌는지
    // 아무도 모른다.** 그대로 보내고 서버가 말하게 둔다.
    const values = lines.split(/\r?\n/)
    setBusy(true)
    setFailure(null)
    setBulk(null)
    try {
      const result = await vocabularyApi.createBulk(
        vocabulary.slug,
        values,
        parent || undefined
      )
      setBulk(result)
      setLines('')
      onAdded()
    } catch (error) {
      setFailure(error instanceof ApiError ? error.message : '더하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  async function submit() {
    if (mode === 'many') return submitMany()
    setBusy(true)
    setFailure(null)
    setResolved(null)
    try {
      const typed = value.trim()
      const added = await vocabularyApi.create(
        vocabulary.slug,
        typed,
        parent || undefined
      )
      onAdded()
      if (added.value !== typed) {
        // 별칭이나 표기 차이로 기존 값에 붙었다 — 말해 주지 않으면 다시 친다.
        setResolved({ typed, got: added.value })
        setValue('')
        return
      }
      setValue('')
    } catch (error) {
      setFailure(error instanceof ApiError ? error.message : '더하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{vocabulary.label} 값 추가</DialogTitle>
          <DialogDescription>
            미리 등록해 두면 사람들이 <b>고르기만</b> 하면 됩니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex gap-1">
            {(['one', 'many'] as const).map((option) => (
              <Button
                key={option}
                size="sm"
                variant={mode === option ? 'default' : 'outline'}
                className="h-7 text-xs"
                onClick={() => {
                  setMode(option)
                  setResolved(null)
                  setBulk(null)
                }}
              >
                {option === 'one' ? '하나씩' : '여러 개'}
              </Button>
            ))}
          </div>

          {mode === 'one' ? (
            <div className="space-y-1.5">
              <Label htmlFor="add-value">값</Label>
              <Input
                id="add-value"
                value={value}
                autoFocus
                onChange={(event) => setValue(event.target.value)}
              />
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="add-values">값 목록</Label>
              {/* **줄 단위가 자연스럽다.** 엑셀에서 열을 복사하면 그대로 붙는다.
                  빈 줄은 건너뛴다 — 붙여 넣기에는 늘 섞여 있고, 그걸 오류로
                  만들면 사람이 손으로 지우게 된다. */}
              <Textarea
                id="add-values"
                value={lines}
                autoFocus
                rows={8}
                placeholder={PLACEHOLDER[vocabulary.parent_slug ? 'child' : 'plain']}
                onChange={(event) => setLines(event.target.value)}
              />
              <p className="text-muted-foreground text-xs">
                한 줄에 하나. 최대 {BULK_MAX}줄. 빈 줄은 건너뜁니다.
                {vocabulary.parent_slug && (
                  <>
                    {' '}
                    줄마다 상위를 달리하려면 <b>상위 &gt; 값</b> 으로 적으세요 (엑셀에서
                    두 열을 복사해도 됩니다). 안 적은 줄은 아래에서 고른 상위로 갑니다.
                  </>
                )}
              </p>
            </div>
          )}

          {vocabulary.parent_slug && (
            // 부모가 있는 축이면 여기서 정해 둔다 — 나중에 따로 잇게 하면
            // 대부분 안 잇는다.
            <VocabularyField
              slug={vocabulary.parent_slug}
              label="상위 분류 (줄에 없을 때)"
              value={parent}
              allowCreate={false}
              onChange={setParent}
            />
          )}

          {bulk && (
            <div className="space-y-1.5 rounded-md border p-2.5">
              <p className="text-sm">
                새로 <b>{bulk.created}</b> · 이미 있던 것 {bulk.existing}
                {bulk.skipped > 0 && ` · 건너뜀 ${bulk.skipped}`}
                {bulk.rejected > 0 && (
                  <span className="text-amber-700 dark:text-amber-500">
                    {' '}
                    · 못 넣음 {bulk.rejected}
                  </span>
                )}
              </p>

              {/* **말없이 버리지 않는다.** 상위를 못 찾은 줄은 그 이유와 함께
                  보여 준다 — 안 보여 주면 목록에 없는 이유를 알 수 없다. */}
              {bulk.items.some((item) => item.status === 'rejected') && (
                <div className="text-xs">
                  <p className="text-amber-700 dark:text-amber-500">못 넣은 줄:</p>
                  <ul className="mt-0.5 space-y-0.5">
                    {bulk.items
                      .filter((item) => item.status === 'rejected')
                      .map((item, index) => (
                        <li
                          key={`${item.input}-${index}`}
                          className="text-muted-foreground"
                        >
                          '{item.input.trim()}' — {item.reason}
                        </li>
                      ))}
                  </ul>
                </div>
              )}
              {/* **어느 것이 안 생겼는지가 알고 싶은 것이다.** 개수만 주면
                  "12개가 새로 생겼습니다" 로 끝나고, 나머지 38개를 찾으러 목록을
                  뒤지게 된다. */}
              {bulk.items.some(
                (item) => item.status === 'existing' && item.value !== item.input.trim()
              ) && (
                <div className="text-xs">
                  <p className="text-muted-foreground">다른 값에 붙은 것:</p>
                  <ul className="mt-0.5 space-y-0.5">
                    {bulk.items
                      .filter(
                        (item) =>
                          item.status === 'existing' && item.value !== item.input.trim()
                      )
                      .map((item, index) => (
                        <li key={`${item.input}-${index}`}>
                          '{item.input.trim()}' → <b>{item.value}</b>
                        </li>
                      ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {resolved && (
            <p className="text-sm text-amber-700 dark:text-amber-500">
              '{resolved.typed}' 는 이미 <b>{resolved.got}</b> 를 가리킵니다 — 새로
              만들지 않았습니다.
            </p>
          )}
          {failure && <p className="text-destructive text-sm">{failure}</p>}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            닫기
          </Button>
          <Button
            onClick={submit}
            disabled={busy || (mode === 'one' ? value.trim() === '' : lines.trim() === '')}
          >
            추가
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
