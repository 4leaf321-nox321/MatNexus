/**
 * 공지 한 건 — **읽고, 관리자는 여기서 고치고 지운다**(2026-09-24).
 *
 * 목록(`NoticesPage`)은 여는 자리다 — VOC 와 같은 짜임이다.
 *
 * **열면 읽음으로 남긴다**(`POST …/read`). 목록의 「새 글」 이 그때 꺼진다. 읽음을 여는
 * 요청(GET)에 묶지 않은 까닭은 서버 쪽에 적었다 — 미리 불러 두는 화면이 남의 읽음을 대신
 * 찍으면 안 된다. 읽음 기록이 실패해도 읽는 것은 막지 않는다.
 */

import { useEffect, useState } from 'react'
import { ArrowLeft, Pencil, Trash2 } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { NoticeBody } from '@/modules/notices/NoticeBody'
import { NoticeDialog } from '@/modules/notices/NoticeDialog'
import { noticesApi, writerOf } from '@/modules/notices/api'
import { useAuth } from '@/shared/auth/AuthContext'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Stamp } from '@/shared/components/Stamp'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { useResource } from '@/shared/hooks/useResource'

export default function NoticeDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const notice = useResource(() => noticesApi.get(id), [id])
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const item = notice.data
  const admin = Boolean(user?.is_system_admin)
  // 발행된 것만 — 초안은 읽음을 셀 글이 아니다.
  const unreadId = item && item.is_published && !item.is_read ? item.id : null

  useEffect(() => {
    if (!unreadId) return
    noticesApi.read(unreadId).catch(() => {
      // 읽음 기록이 실패하면 목록에 「새 글」 이 남을 뿐이다 — 읽는 것은 막지 않는다.
    })
  }, [unreadId])

  return (
    <div className="mx-auto max-w-4xl">
      <Link
        to="/notices"
        className="text-muted-foreground hover:text-foreground mb-3 inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" />
        공지 목록
      </Link>

      <ErrorNotice error={notice.error ?? error} className="mb-4" />

      {item && (
        <>
          <header className="mb-4">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold">{item.title}</h1>
              {!item.is_published && (
                <Badge variant="outline" className="text-muted-foreground">
                  초안
                </Badge>
              )}
              {item.is_popup && <Badge variant="outline">팝업</Badge>}
              {admin && (
                <div className="ml-auto flex shrink-0 gap-1">
                  <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
                    <Pencil className="size-3.5" />
                    편집
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setDeleting(true)}>
                    <Trash2 className="size-3.5" />
                    삭제
                  </Button>
                </div>
              )}
            </div>
            <p className="text-muted-foreground mt-1 text-sm">
              {writerOf(item)} · <Stamp at={item.published_at ?? item.created_at} />
            </p>
          </header>

          <section className="mb-6 rounded-md border p-4">
            <NoticeBody text={item.body} />
          </section>

          <NoticeDialog
            open={editing}
            notice={item}
            onClose={() => setEditing(false)}
            onDone={() => {
              setEditing(false)
              notice.reload()
            }}
          />

          {/* **「내리기」 를 함께 말한다.** 잘못 올린 것을 잠깐 감추는 것과 아예
              없애는 것은 다른 일인데, 사람은 그 자리에서 삭제부터 누른다. */}
          <ConfirmDialog
            open={deleting}
            title="공지를 지웁니다"
            busy={busy}
            body={
              <>
                <b>{item.title}</b> 과 그 읽음 기록이 사라집니다.
                <p className="text-muted-foreground mt-2">
                  잠깐 감추려는 것이면 지우지 말고 <b>편집에서 발행을 끄세요</b> — 내용과
                  발행 시각이 남습니다.
                </p>
              </>
            }
            onClose={() => setDeleting(false)}
            onConfirm={async () => {
              setBusy(true)
              setError(null)
              try {
                await noticesApi.remove(item.id)
                navigate('/notices')
              } catch (caught) {
                setError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
                setDeleting(false)
              } finally {
                setBusy(false)
              }
            }}
          />
        </>
      )}
    </div>
  )
}
