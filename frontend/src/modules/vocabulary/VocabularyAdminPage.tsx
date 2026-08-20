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
import { Eye, EyeOff, Pencil, RefreshCw } from 'lucide-react'

import { vocabularyApi } from '@/modules/vocabulary/api'
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
  const [error, setError] = useState<Error | null>(null)
  // 검색은 서버가 한다 — 어휘가 수만 개가 되면 전체를 받을 수 없다.
  const terms = useResource(
    () => vocabularyApi.search(vocabulary.slug, term, showHidden, leastUsed),
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
          className="ml-auto h-8 text-xs"
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

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>값</TableHead>
            <TableHead className="text-right">쓰는 곳</TableHead>
            <TableHead className="w-32" />
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
              {/* **몇 건이 따라오는지 보여 준다.** 이름 고치기가 가벼운 조작처럼
                  보이지만 외래키라 이 수만큼이 함께 바뀐다. */}
              <TableCell className="text-right tabular-nums">{item.usage_count}</TableCell>
              <TableCell className="text-right">
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

      {!terms.loading && rows.length === 0 && (
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
