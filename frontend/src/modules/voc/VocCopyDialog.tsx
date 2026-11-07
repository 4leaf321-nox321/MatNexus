/**
 * VOC 내용 복사 — **범위를 정해 모아 보여 주고, 「복사」 를 누르면 복사한다** (2026-11-07).
 *
 * ## 범위는 둘이다
 *
 * - **고른 건**: 표에서 체크한 것. Shift 를 누른 채 고르면 사이의 건까지 한꺼번에 골라진다
 *   (`VocPage`). 고른 것은 거르기와 상관없이 그대로 모은다 — 쪽을 넘겨 가며 고른 것이다.
 * - **번호 범위**: 「12 ~ 30」. 쪽을 넘지 않고 큰 범위를 잡는 길이다. 지금 거른 조건(상태 ·
 *   찾기 · 내가 낸 것만) 안에서 모은다 — 화면에 보이는 것과 다른 것이 복사되면 사람은 모른 채
 *   붙여 넣는다. 비우면 그쪽 끝까지다.
 *
 * ## 왜 두 걸음인가
 *
 * 사내망에서 HTTP 로 열면 복사는 **누른 그 순간**에만 된다(`shared/lib/clipboard`). 서버에서 받아
 * 온 뒤에 복사하면 그 순간이 지나 조용히 실패한다 — 공지 복사(`NoticeCopyDialog`)와 같은 까닭으로
 * 먼저 모아 보여 주고, 「복사」 는 다 모인 뒤에 누른다.
 *
 * **범위 칸을 고쳤는데 「모으기」 를 안 눌렀으면 복사를 막는다.** 칸에는 새 범위가 적혀 있는데
 * 글은 옛 범위라, 그대로 복사하면 사람은 새 범위를 복사한 줄 안다.
 */

import { useMemo, useState } from 'react'
import { Check, Copy } from 'lucide-react'

import { vocApi } from '@/modules/voc/api'
import { rangeLabel, vocAsText } from '@/modules/voc/copyAll'
import { fetchAll } from '@/shared/api/paging'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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
import { useResource } from '@/shared/hooks/useResource'
import { copyText } from '@/shared/lib/clipboard'

export interface VocBoardFilters {
  status: string
  /** 상태 칩의 이름 — 복사한 글의 머리에 적는다. */
  statusLabel?: string
  q: string
  mine: boolean
}

/** 번호 칸의 글자를 번호로. 1 보다 작거나 숫자가 아니면 「비움」 이다. */
function toSeq(text: string): number | undefined {
  const value = Number.parseInt(text, 10)
  return Number.isFinite(value) && value >= 1 ? value : undefined
}

function seqText(value: number | undefined): string {
  return value ? String(value) : ''
}

/** 열릴 때마다 새로 선다(`VocPage` 가 열 때만 그린다) — 지난번 범위 · 복사 결과가 안 남는다. */
export function VocCopyDialog({
  picked,
  filters,
  onClose,
}: {
  /** 표에서 고른 건. 비었으면 번호 범위만 있다. */
  picked: string[]
  filters: VocBoardFilters
  onClose: () => void
}) {
  const [mode, setMode] = useState<'picked' | 'range'>(picked.length > 0 ? 'picked' : 'range')
  const [typed, setTyped] = useState({ from: '', to: '' })
  const [range, setRange] = useState<{ from?: number; to?: number }>({})
  const [copied, setCopied] = useState<'yes' | 'no' | null>(null)
  // 부르는 쪽이 그릴 때마다 새 배열을 주므로 내용으로 견준다 — 아니면 그릴 때마다 다시 모은다.
  const pickedKey = picked.join(',')
  const filtered = Boolean(filters.status || filters.q || filters.mine)

  const collected = useResource(async () => {
    const at = new Date()
    if (mode === 'picked') {
      const items = await vocApi.contentsOf(picked)
      return { items, total: picked.length, at }
    }
    const page = await fetchAll((limit, offset) =>
      vocApi.contents({
        status: filters.status || undefined,
        q: filters.q || undefined,
        mine: filters.mine,
        seqFrom: range.from,
        seqTo: range.to,
        limit,
        offset,
      })
    )
    return { items: page.items, total: page.total, at }
  }, [mode, pickedKey, range.from, range.to, filters.status, filters.q, filters.mine])

  const dirty =
    mode === 'range' && (typed.from !== seqText(range.from) || typed.to !== seqText(range.to))
  const ready = !collected.loading && collected.data !== null
  const text = useMemo(
    () =>
      ready && collected.data
        ? vocAsText(collected.data.items, {
            total: collected.data.total,
            picked: mode === 'picked',
            seqFrom: range.from,
            seqTo: range.to,
            statusLabel: filters.status ? (filters.statusLabel ?? filters.status) : undefined,
            q: filters.q || undefined,
            mine: filters.mine,
            at: collected.data.at,
          })
        : '',
    [ready, collected.data, mode, range.from, range.to, filters]
  )

  function apply(event: React.FormEvent) {
    event.preventDefault()
    let from = toSeq(typed.from)
    let to = toSeq(typed.to)
    // 거꾸로 적었으면 바로잡는다 — 「30 ~ 12」 를 빈 결과로 돌려주면 사람은 VOC 가 없는 줄 안다.
    if (from && to && from > to) [from, to] = [to, from]
    setTyped({ from: seqText(from), to: seqText(to) })
    setRange({ from, to })
    setCopied(null)
  }

  async function copy() {
    if (!text || dirty) return
    // **기다리지 않고 바로** — 글은 이미 모여 있다. 누른 그 순간에 복사해야 HTTP 에서도 된다.
    const ok = await copyText(text)
    setCopied(ok ? 'yes' : 'no')
    if (ok) window.setTimeout(() => setCopied(null), 2000)
  }

  const items = collected.data?.items ?? []
  const total = collected.data?.total ?? 0
  const rangeNote = mode === 'range' ? rangeLabel(range.from, range.to) : null

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>VOC 내용 복사</DialogTitle>
          <DialogDescription>
            VOC 를 최근 것부터 글 하나로 모았습니다 — 번호 · 제목 · 상태 · 올린 사람 · 날짜 · 본문 ·
            이력. 다른 문서나 메신저에 붙여 넣으세요.
          </DialogDescription>
        </DialogHeader>

        {picked.length > 0 && (
          <div className="flex flex-wrap gap-4 text-sm" role="radiogroup" aria-label="복사할 범위">
            <label className="flex items-center gap-1.5">
              <input
                type="radio"
                name="voc-copy-mode"
                checked={mode === 'picked'}
                onChange={() => {
                  setMode('picked')
                  setCopied(null)
                }}
              />
              고른 {picked.length.toLocaleString('ko-KR')}건
            </label>
            <label className="flex items-center gap-1.5">
              <input
                type="radio"
                name="voc-copy-mode"
                checked={mode === 'range'}
                onChange={() => {
                  setMode('range')
                  setCopied(null)
                }}
              />
              번호 범위
            </label>
          </div>
        )}

        {mode === 'picked' ? (
          <p className="text-sm">
            표에서 고른 건만 모읍니다 — 거른 조건과 상관없이. 표에서 Shift 를 누른 채 고르면 사이의
            건까지 한꺼번에 골라집니다.
          </p>
        ) : (
          <form className="flex flex-wrap items-end gap-2" onSubmit={apply}>
            <div className="space-y-1">
              <Label htmlFor="voc-copy-from">번호 시작</Label>
              <Input
                id="voc-copy-from"
                type="number"
                min={1}
                inputMode="numeric"
                className="w-28"
                placeholder="처음"
                value={typed.from}
                onChange={(event) => setTyped({ ...typed, from: event.target.value })}
              />
            </div>
            <span className="pb-2">~</span>
            <div className="space-y-1">
              <Label htmlFor="voc-copy-to">번호 끝</Label>
              <Input
                id="voc-copy-to"
                type="number"
                min={1}
                inputMode="numeric"
                className="w-28"
                placeholder="끝"
                value={typed.to}
                onChange={(event) => setTyped({ ...typed, to: event.target.value })}
              />
            </div>
            <Button type="submit" variant="outline">
              모으기
            </Button>
            <p className="basis-full text-sm">
              비우면 그쪽 끝까지입니다. 두 끝 번호도 들어갑니다.
              {filtered && ' 지금 거른 조건(상태 · 찾기 · 내가 낸 것만)에 맞는 것만입니다.'}
            </p>
          </form>
        )}

        <ErrorNotice error={collected.error} />

        <textarea
          readOnly
          aria-label="VOC 내용"
          rows={16}
          className="border-input bg-muted/40 w-full rounded-md border px-3 py-2 text-sm"
          value={ready ? text : '모으는 중…'}
          // 눌러서 전부 고른다 — 복사가 막힌 브라우저에서 사람이 직접 복사하는 길이다.
          onFocus={(event) => event.currentTarget.select()}
        />

        {ready && (
          <p className="text-sm" role="status">
            {rangeNote && `${rangeNote} · `}
            VOC {items.length.toLocaleString('ko-KR')}건 · {text.length.toLocaleString('ko-KR')}자
            {items.length < total &&
              (mode === 'picked'
                ? ` — 고른 ${total.toLocaleString('ko-KR')}건 중 나머지는 그 사이 지워졌습니다.`
                : ` — 전체 ${total.toLocaleString('ko-KR')}건 중 일부만 모았습니다. 번호 범위로 좁혀 나눠 복사하세요.`)}
          </p>
        )}
        {dirty && (
          <p className="text-destructive text-sm" role="alert">
            범위를 바꿨습니다 — 「모으기」 를 눌러야 새 범위가 모입니다.
          </p>
        )}
        {copied === 'no' && (
          <p className="text-destructive text-sm" role="alert">
            브라우저가 복사를 막았습니다 — 위 글을 눌러 전부 고른 뒤 Ctrl+C 로 복사하세요.
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
          <Button onClick={() => void copy()} disabled={!ready || !text || dirty}>
            {copied === 'yes' ? <Check className="size-4" /> : <Copy className="size-4" />}
            {copied === 'yes' ? '복사했습니다' : '복사'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
