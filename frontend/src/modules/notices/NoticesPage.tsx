/**
 * 공지 — **게시판이다**(2026-09-24). 읽기는 모두, 쓰기는 시스템 관리자.
 *
 * 폐쇄망에서 **배포 없이 안내를 갱신하는 유일한 수단**이다. 그래서 관리자가
 * 이 화면에서 바로 쓰고 발행할 수 있어야 한다.
 *
 * ## 카드 더미에서 게시판으로
 *
 * 전에는 본문까지 카드로 쌓았다. 공지가 늘자 찾을 길이 없었고, 같은 진입점의 VOC 는
 * 이미 게시판이라(번호·검색·쪽 넘기기·한 건 상세) 두 탭이 서로 다르게 굴었다. 이제 같은
 * 모양이다 — 목록은 여는 자리이고, 본문·편집·삭제는 상세(`/notices/:id`)에서 한다.
 *
 * **안 읽은 글이 보인다.** 굵게 적고 「새 글」 을 붙인다 — 팝업은 중요한 것에만 켜므로,
 * 나머지는 여기서 알아채야 한다. 사이드바에도 그 수가 선다(`useUnreadNotices`).
 *
 * **「모두 읽음」 이 있다.** 처음 들어온 사람에게는 그동안 쌓인 공지가 전부 새 글이다 —
 * 하나씩 열어 끄라고 하면 사이드바의 수를 안 보게 된다.
 */

import { useState } from 'react'
import { CheckCheck, Megaphone, Plus, Search } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { NoticeDialog } from '@/modules/notices/NoticeDialog'
import { noticesApi, writerOf } from '@/modules/notices/api'
import { useAuth } from '@/shared/auth/AuthContext'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Stamp } from '@/shared/components/Stamp'
import { SubTabs } from '@/shared/components/SubTabs'
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
import { ROW_FOCUS_STYLE, useRowFocus } from '@/shared/hooks/useRowFocus'

const PAGE = 50

export default function NoticesPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  // 치는 글자와 적용된 글자를 가른다 — 한 글자마다 목록을 다시 부르지 않는다.
  const [typed, setTyped] = useState('')
  const [q, setQ] = useState('')
  const [unread, setUnread] = useState(false)
  const [offset, setOffset] = useState(0)
  const [writing, setWriting] = useState(false)

  const page = useResource(
    () => noticesApi.list({ q: q || undefined, unread, limit: PAGE, offset }),
    [q, unread, offset]
  )
  const rows = page.data?.items ?? []
  const total = page.data?.total ?? 0
  const focus = useRowFocus(rows.map((one) => one.id))
  // 이 쪽에 안 보이는 안 읽은 글도 센다 — 목록은 쪽으로 잘려 있다.
  const unreadCount = useResource(() => noticesApi.unreadCount(), [])
  const unreadTotal = unreadCount.data?.unread ?? 0
  const [marking, setMarking] = useState(false)
  const [markError, setMarkError] = useState<Error | null>(null)

  const readAll = async () => {
    setMarking(true)
    setMarkError(null)
    try {
      await noticesApi.readAll()
      page.reload()
      unreadCount.reload()
    } catch (caught) {
      setMarkError(caught instanceof Error ? caught : new Error('읽음으로 바꾸지 못했습니다.'))
    } finally {
      setMarking(false)
    }
  }

  return (
    // 표라 폭을 스스로 좁히지 않는다(`boundaries.test`). 읽는 화면인 상세만 좁힌다.
    <div>
      {/* **공지와 VOC 는 한 진입점이다.** 메뉴에 둘로 서 있으면 「어느 쪽에
          쓰지」 를 매번 묻는다 — 위에서 내려오는 글과 아래에서 올라가는 글일
          뿐, 사람에게는 같은 게시판이다. */}
      <SubTabs
        items={[
          { to: '/notices', label: '공지' },
          { to: '/voc', label: 'VOC' },
        ]}
      />
      <PageHeader
        title="공지"
        description="배포 없이 안내를 갱신할 수 있는 곳입니다. 새 기능 안내도 배포와 함께 여기 올라옵니다."
        actions={
          user?.is_system_admin && (
            <Button onClick={() => setWriting(true)}>
              <Plus className="size-4" />
              공지 작성
            </Button>
          )
        }
      />

      <ErrorNotice error={page.error ?? markError} className="mb-4" />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={unread}
            onChange={(event) => {
              setOffset(0)
              setUnread(event.target.checked)
            }}
          />
          안 읽은 것만
        </label>
        {unreadTotal > 0 && (
          <Button size="sm" variant="outline" disabled={marking} onClick={readAll}>
            <CheckCheck className="size-4" />
            모두 읽음 ({unreadTotal})
          </Button>
        )}
        <form
          className="relative ml-auto w-full sm:w-64"
          onSubmit={(event) => {
            event.preventDefault()
            setOffset(0)
            setQ(typed.trim())
          }}
        >
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            placeholder="제목·내용으로 찾기"
            aria-label="공지 찾기"
            className="pl-8"
          />
        </form>
      </div>

      {!page.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          <Megaphone className="mx-auto mb-2 size-5 opacity-50" />
          {q || unread ? '거른 조건에 맞는 공지가 없습니다.' : '공지가 없습니다.'}
        </div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16 text-right">번호</TableHead>
                <TableHead>제목</TableHead>
                <TableHead className="w-32">올린 사람</TableHead>
                <TableHead className="w-36">올린 날짜</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((notice, at) => (
                <TableRow
                  key={notice.id}
                  className={`cursor-pointer ${ROW_FOCUS_STYLE}`}
                  {...focus.rowProps(notice.id)}
                  // 줄 어디를 눌러도 연다. 키보드는 제목 링크가 받는다(`useRowFocus`).
                  onClick={() => navigate(`/notices/${notice.id}`)}
                >
                  {/* **번호는 게시판의 차례다** — 가장 오래된 것이 1. 저장된 값이 아니라
                      지우면 당겨진다(공지는 번호로 부르는 일이 없다). */}
                  <TableCell className="text-right tabular-nums">{total - offset - at}</TableCell>
                  <TableCell>
                    <Link
                      to={`/notices/${notice.id}`}
                      // 굵게는 **알릴 글**에만 — 초안은 아직 아무에게도 안 알렸다.
                      className={`hover:underline ${notice.is_read || !notice.is_published ? '' : 'font-semibold'}`}
                      onClick={(event) => event.stopPropagation()}
                    >
                      {notice.title}
                    </Link>
                    {!notice.is_read && notice.is_published && (
                      <Badge className="ml-2">새 글</Badge>
                    )}
                    {!notice.is_published && (
                      <Badge variant="outline" className="text-muted-foreground ml-2">
                        초안
                      </Badge>
                    )}
                    {notice.is_popup && (
                      <Badge variant="outline" className="ml-2">
                        팝업
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>{writerOf(notice)}</TableCell>
                  <TableCell>
                    <Stamp at={notice.published_at ?? notice.created_at} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {total > PAGE && (
        <div className="mt-3 flex items-center justify-between text-sm">
          <span className="text-muted-foreground tabular-nums">
            {offset + 1}–{Math.min(offset + PAGE, total)} / {total}건
          </span>
          <div className="flex gap-1">
            <Button
              size="sm"
              variant="outline"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE))}
            >
              이전
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={offset + PAGE >= total}
              onClick={() => setOffset(offset + PAGE)}
            >
              다음
            </Button>
          </div>
        </div>
      )}

      <NoticeDialog
        open={writing}
        notice={null}
        onClose={() => setWriting(false)}
        onDone={(saved) => {
          setWriting(false)
          navigate(`/notices/${saved.id}`)
        }}
      />
    </div>
  )
}
