/**
 * 한 시편의 시험들 — 재료 상세에 끼워 넣는 조각.
 *
 * 시험 UI 를 시험 모듈이 갖고 있고, 재료 화면은 **자리만 내어 준다.** 워크벤치
 * 규칙(R5)과 같은 이유다 — 도메인 로직이 남의 화면에 쌓이기 시작하면 그 화면이
 * 모든 도메인을 알게 된다.
 *
 * ## 골라 지운다(2026-10-20)
 *
 * 사용자 보고: 잘못된 옵션으로 올린 시험을 하나씩 열어 지워야 했다. 줄마다 고르는 칸을 두고,
 * 「실패만 고르기」 로 읽기에 실패한 것을 한 번에 고른다. 지우는 길은 시험 목록과 같은
 * `POST /test-runs/delete` 다 — 막힌 것은 이유와 함께 돌아온다.
 */

import { useEffect, useState } from 'react'
import { AlertTriangle, Plus, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { RUN_STATUS_LABEL, isPending, testsApi } from '@/modules/tests/api'
import { UploadDialog } from '@/modules/tests/UploadDialog'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { useResource } from '@/shared/hooks/useResource'
import { useRowSelection } from '@/shared/hooks/useRowSelection'

interface Props {
  specimenId: string
  specimenName: string
  /** 시험을 지웠다 — 시편 표의 시험 수 · 실패 수가 달라진다. */
  onChanged?: () => void
}

export function SpecimenTests({ specimenId, specimenName, onChanged }: Props) {
  const [uploading, setUploading] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const runs = useResource(() => testsApi.runs({ specimen_id: specimenId }), [specimenId])
  const rows = runs.data?.items ?? []
  const pending = rows.some((run) => isPending(run.status))
  const selection = useRowSelection(rows.map((run) => run.id))
  const picked = rows.filter((run) => selection.picked.has(run.id))
  const failed = rows.filter((run) => run.status === 'failed')

  // 올린 직후에는 워커가 아직 읽는 중이다. 사용자가 새로고침을 눌러야 결과가
  // 보이면, 비동기로 처리하는 이득이 사용자에게 가지 않는다.
  useEffect(() => {
    if (!pending) return
    const timer = setInterval(() => runs.reload(), 3000)
    return () => clearInterval(timer)
  }, [pending, runs])

  async function removePicked() {
    setBusy(true)
    try {
      const done = await testsApi.removeMany(picked.map((run) => run.id))
      // **조용히 세지 않는다.** 무엇이 안 지워졌는지 말해야 다시 고를 수 있다.
      setNotice(
        `시험 ${done.deleted}건을 지웠습니다.` +
          (done.blocked.length > 0 ? ` 못 지운 것: ${done.blocked.join(', ')}` : '')
      )
      selection.clear()
      setRemoving(false)
      runs.reload()
      onChanged?.()
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : '지우지 못했습니다.')
      setRemoving(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-2 border-t pt-2">
      <div className="mb-1 flex flex-wrap items-center gap-1">
        <span className="text-muted-foreground text-xs">
          시험 {rows.length}건{pending && ' · 읽는 중'}
        </span>
        {/* **잘못 올린 것은 대개 읽기에 실패한다** — 한 번에 고르는 자리. */}
        {failed.length > 0 && (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs"
            onClick={() => selection.replace(failed.map((run) => run.id))}
          >
            <AlertTriangle className="text-destructive size-3.5" />
            실패만 고르기 ({failed.length})
          </Button>
        )}
        <span className="ml-auto flex items-center gap-1">
          {picked.length > 0 && (
            <>
              <span className="text-xs">
                <b>{picked.length}건</b> 선택
              </span>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={() => selection.clear()}
              >
                선택 해제
              </Button>
              <Button
                size="sm"
                variant="destructive"
                className="h-7 text-xs"
                onClick={() => {
                  setNotice(null)
                  setRemoving(true)
                }}
              >
                <Trash2 className="size-3.5" />
                삭제
              </Button>
            </>
          )}
          <Button size="sm" variant="ghost" onClick={() => setUploading(true)}>
            <Plus className="size-3.5" />
            시험 등록
          </Button>
        </span>
      </div>

      {notice && <p className="mb-1 text-xs">{notice}</p>}

      {rows.length > 0 && (
        <ul className="space-y-1">
          {rows.map((run) => (
            <li key={run.id} className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                aria-label={`${run.record_name} 선택`}
                checked={selection.picked.has(run.id)}
                // **`onClick` 이다** — `onChange` 에는 Shift 가 안 실린다.
                onClick={(event) => selection.toggle(run.id, event)}
                onChange={() => {}}
              />
              <Link
                to={`/test-runs/${run.id}`}
                className="hover:text-primary font-mono hover:underline"
              >
                {run.record_name}
              </Link>
              <Badge
                variant={
                  run.status === 'failed'
                    ? 'destructive'
                    : run.status === 'parsed'
                      ? 'secondary'
                      : 'outline'
                }
              >
                {RUN_STATUS_LABEL[run.status] ?? run.status}
              </Badge>
              {run.warnings.length > 0 && <AlertTriangle className="size-3 text-amber-500" />}
              {run.row_count != null && (
                <span className="text-muted-foreground ml-auto tabular-nums">
                  {run.row_count.toLocaleString('ko-KR')}행
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={removing}
        busy={busy}
        title={`시험 ${picked.length}건을 지웁니다`}
        undoable="휴지통에서 되살릴 수 있습니다."
        body={
          <>
            <p className="mb-2">
              고른 <b>{picked.length}건</b>이 목록에서 사라집니다. 원본 파일과 처리 결과도
              함께 가려집니다.
            </p>
            <ul className="text-muted-foreground max-h-40 space-y-0.5 overflow-y-auto font-mono text-xs">
              {picked.map((run) => (
                <li key={run.id}>{run.record_name}</li>
              ))}
            </ul>
          </>
        }
        onConfirm={() => void removePicked()}
        onClose={() => setRemoving(false)}
      />

      <UploadDialog
        specimenId={specimenId}
        specimenName={specimenName}
        open={uploading}
        onClose={() => setUploading(false)}
        onDone={() => {
          setUploading(false)
          runs.reload()
          onChanged?.()
        }}
      />
    </div>
  )
}
