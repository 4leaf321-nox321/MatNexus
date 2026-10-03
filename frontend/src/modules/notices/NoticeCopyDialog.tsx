/**
 * 공지 내용 복사 — **모아서 보여 주고, 「복사」 를 누르면 복사한다** (2026-10-03).
 *
 * ## 왜 두 걸음인가
 *
 * 사내망에서 HTTP 로 열면 복사는 **누른 그 순간**에만 된다(`shared/lib/clipboard`). 단추를 누르고
 * 서버에서 공지를 다 받아 온 뒤에 복사하면 그 순간이 지나 조용히 실패한다 — 사람은 복사된 줄
 * 알고 빈 것을 붙여 넣는다. 그래서 먼저 모아 보여 주고, 「복사」 는 다 모인 뒤에 누른다. 글이
 * 보이므로 복사가 막힌 브라우저에서도 골라서 직접 복사할 수 있다(아이디 내보내기와 같은 짜임).
 *
 * ## 화면에 보이는 것 그대로 — 거른 조건까지
 *
 * 찾기 · 「안 읽은 것만」 으로 걸러 두었으면 그것만 모은다. 화면과 다른 것이 복사되면 사람은 그
 * 사실을 모른 채 붙여 넣는다 — 걸렀으면 그렇다고 위에 적고, 복사한 글의 머리에도 적는다.
 * 쪽은 넘겨 가며 전부 모은다(`fetchAll` — 2,000건에서 멈추고 그렇다고 말한다).
 */

import { useMemo, useState } from 'react'
import { Check, Copy } from 'lucide-react'

import { noticesApi } from '@/modules/notices/api'
import { noticesAsText } from '@/modules/notices/copyAll'
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
import { useResource } from '@/shared/hooks/useResource'
import { copyText } from '@/shared/lib/clipboard'

export function NoticeCopyDialog({
  open,
  q,
  unread,
  onClose,
}: {
  open: boolean
  /** 게시판에서 지금 거른 조건 — 그대로 모은다. */
  q: string
  unread: boolean
  onClose: () => void
}) {
  const collected = useResource(async () => {
    if (!open) return null
    const page = await fetchAll((limit, offset) =>
      noticesApi.list({ q: q || undefined, unread, limit, offset })
    )
    return { page, at: new Date() }
  }, [open, q, unread])
  const [copied, setCopied] = useState<'yes' | 'no' | null>(null)

  const page = collected.data?.page ?? null
  const text = useMemo(
    () =>
      collected.data
        ? noticesAsText(collected.data.page.items, {
            total: collected.data.page.total,
            q: q || undefined,
            unread,
            at: collected.data.at,
          })
        : '',
    [collected.data, q, unread]
  )
  const filtered = Boolean(q) || unread

  /** 닫을 때 지난번 복사 결과를 지운다 — 다시 열었을 때 옛 「막았습니다」 가 남지 않게. */
  function close() {
    setCopied(null)
    onClose()
  }

  async function copy() {
    if (!text) return
    // **기다리지 않고 바로** — 글은 이미 모여 있다. 누른 그 순간에 복사해야 HTTP 에서도 된다.
    const ok = await copyText(text)
    setCopied(ok ? 'yes' : 'no')
    if (ok) window.setTimeout(() => setCopied(null), 2000)
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && close()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>공지 내용 복사</DialogTitle>
          <DialogDescription>
            게시판의 공지를 최근 것부터 글 하나로 모았습니다 — 번호 · 제목 · 올린 사람 · 날짜 · 본문.
            다른 문서나 메신저에 붙여 넣으세요.
            {filtered && ' 지금 거른 조건(찾기 · 안 읽은 것만)에 맞는 것만입니다.'}
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={collected.error} />

        <textarea
          readOnly
          aria-label="공지 내용"
          rows={16}
          className="border-input bg-muted/40 w-full rounded-md border px-3 py-2 text-sm"
          value={collected.loading && !collected.data ? '모으는 중…' : text}
          // 눌러서 전부 고른다 — 복사가 막힌 브라우저에서 사람이 직접 복사하는 길이다.
          onFocus={(event) => event.currentTarget.select()}
        />

        {page && (
          <p className="text-sm" role="status">
            공지 {page.items.length.toLocaleString('ko-KR')}건 · {text.length.toLocaleString('ko-KR')}자
            {page.items.length < page.total &&
              ` — 전체 ${page.total.toLocaleString('ko-KR')}건 중 일부만 모았습니다. 찾기로 좁혀 나눠 복사하세요.`}
          </p>
        )}
        {copied === 'no' && (
          <p className="text-destructive text-sm" role="alert">
            브라우저가 복사를 막았습니다 — 위 글을 눌러 전부 고른 뒤 Ctrl+C 로 복사하세요.
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={close}>
            닫기
          </Button>
          <Button onClick={() => void copy()} disabled={!text}>
            {copied === 'yes' ? <Check className="size-4" /> : <Copy className="size-4" />}
            {copied === 'yes' ? '복사했습니다' : '복사'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
