/**
 * 어휘 관리 — **잘못 들어간 값을 고칠 자리.**
 *
 * 어휘를 켜 두고 관리 화면이 없으면 절반만 한 것이다. `'???'` 같은 값이
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

import { useState } from 'react'
import { Eye, EyeOff, GitMerge, Pencil, Plus, RefreshCw, Tag, X } from 'lucide-react'

import { vocabularyApi } from '@/modules/vocabulary/api'
import { VocabularyField } from '@/modules/vocabulary/VocabularyField'
import type { Term, Vocabulary } from '@/modules/vocabulary/api'
import { ApiError } from '@/shared/api/client'
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

export default function VocabularyAdminPage() {
  const vocabularies = useResource(() => vocabularyApi.list(), [])
  const [slug, setSlug] = useState<string | null>(null)
  const axes = vocabularies.data ?? []
  const active = axes.find((item) => item.slug === slug) ?? axes[0] ?? null

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="어휘"
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

      {active && <TermTable vocabulary={active} />}
    </div>
  )
}

function TermTable({ vocabulary }: { vocabulary: Vocabulary }) {
  const [term, setTerm] = useState('')
  const [showHidden, setShowHidden] = useState(false)
  const [leastUsed, setLeastUsed] = useState(false)
  const [editing, setEditing] = useState<Term | null>(null)
  const [detail, setDetail] = useState<Term | null>(null)
  const [showCandidates, setShowCandidates] = useState(false)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  // 검색은 서버가 한다 — 어휘가 수만 개가 되면 전체를 받을 수 없다.
  const terms = useResource(
    () => vocabularyApi.search(vocabulary.slug, term, {
        includeHidden: showHidden,
        leastUsed,
      }),
    [vocabulary.slug, term, showHidden, leastUsed]
  )

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

  const rows = terms.data ?? []

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

      {showCandidates ? (
        <MergeCandidates slug={vocabulary.slug} onChanged={() => terms.reload()} />
      ) : (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>값</TableHead>
            <TableHead>상위</TableHead>
            <TableHead className="text-right">쓰는 곳</TableHead>
            <TableHead className="w-40" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((item) => (
            <TableRow key={item.id} className={item.status === 'deprecated' ? 'opacity-50' : ''}>
              <TableCell>
                {item.value}
                {item.status === 'deprecated' && (
                  <Badge variant="outline" className="ml-2 text-xs">
                    감춤
                  </Badge>
                )}
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">
                {item.parent_value ?? '—'}
              </TableCell>
              {/* **몇 건이 따라오는지 보여 준다.** 이름 고치기가 가벼운 조작처럼
                  보이지만 외래키라 이 수만큼이 함께 바뀐다. */}
              <TableCell className="text-right tabular-nums">{item.usage_count}</TableCell>
              <TableCell className="text-right">
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
function AddTermDialog({
  vocabulary,
  onClose,
  onAdded,
}: {
  vocabulary: Vocabulary
  onClose: () => void
  onAdded: () => void
}) {
  const [value, setValue] = useState('')
  const [parent, setParent] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [resolved, setResolved] = useState<{ typed: string; got: string } | null>(null)

  async function submit() {
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
          <div className="space-y-1.5">
            <Label htmlFor="add-value">값</Label>
            <Input
              id="add-value"
              value={value}
              autoFocus
              onChange={(event) => setValue(event.target.value)}
            />
          </div>

          {vocabulary.parent_slug && (
            // 부모가 있는 축이면 여기서 정해 둔다 — 나중에 따로 잇게 하면
            // 대부분 안 잇는다.
            <VocabularyField
              slug={vocabulary.parent_slug}
              label="상위 분류 (선택)"
              value={parent}
              allowCreate={false}
              onChange={setParent}
            />
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
          <Button onClick={submit} disabled={busy || value.trim() === ''}>
            추가
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
