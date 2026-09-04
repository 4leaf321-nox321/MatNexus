/**
 * ReportArchive 부서 트리 가져오기 — **계획을 보고 누른다.**
 *
 * 조직도는 한 번 잘못 들어가면 지우기 어렵다(부서마다 재료·시험이 매달리기
 * 시작한다). 그래서 파일을 고르면 **바로 만들지 않고** 무엇이 만들어질지 먼저
 * 보여 준다 — 만들 것·건너뛸 것·오류를 줄마다.
 *
 * 오류가 있어도 **막지 않는다.** TF 아래 행 하나 때문에 부서 마흔 개를 못 들여오면
 * 사람은 파일을 손으로 고치기 시작하고, 고친 파일은 원본과 갈린다. 오류 줄은
 * 남겨 두고 되는 것만 들여온다 — 무엇이 안 들어왔는지는 결과가 말한다.
 */

import { FileUp, Loader2 } from 'lucide-react'
import { useRef, useState } from 'react'

import { workspacesApi } from '@/modules/workspaces/api'
import type { WorkspaceImportResult, WorkspaceImportRow } from '@/modules/workspaces/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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

const ACTION_LABEL: Record<string, string> = {
  create: '만듭니다',
  skip_exists: '이미 있음',
  skip_kind: '대상 아님',
  error: '오류',
}

function RowBadge({ row }: { row: WorkspaceImportRow }) {
  const variant =
    row.action === 'create' ? 'default' : row.action === 'error' ? 'destructive' : 'secondary'
  return (
    <Badge variant={variant} className="shrink-0 text-[10px]">
      {ACTION_LABEL[row.action] ?? row.action}
    </Badge>
  )
}

export function ImportWorkspacesDialog({
  open,
  onClose,
  onDone,
}: {
  open: boolean
  onClose: () => void
  /** 들여온 뒤 트리를 다시 읽는다. */
  onDone: () => void
}) {
  const picker = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<WorkspaceImportResult | null>(null)
  const [done, setDone] = useState<WorkspaceImportResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  function reset() {
    setFile(null)
    setPreview(null)
    setDone(null)
    setError(null)
  }

  async function pick(next: File) {
    setFile(next)
    setPreview(null)
    setDone(null)
    setError(null)
    setBusy(true)
    try {
      setPreview(await workspacesApi.previewImport(next))
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('파일을 읽지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  async function run() {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      setDone(await workspacesApi.runImport(file))
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('가져오지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const shown = done ?? preview

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          reset()
          onClose()
        }
      }}
    >
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>ReportArchive 부서 트리 가져오기</DialogTitle>
          <DialogDescription>
            ReportArchive 의 시스템 관리 &gt; 「부서 정보 내보내기」 가 만든 CSV(부서정보.csv)를
            그대로 올립니다. 이미 있는 부서는 건드리지 않습니다 — 새로 생긴 부서만 들어옵니다.
          </DialogDescription>
        </DialogHeader>

        <input
          ref={picker}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          aria-label="부서 CSV 파일"
          onChange={(event) => {
            const next = event.target.files?.[0]
            if (next) void pick(next)
            // 같은 파일을 다시 골라도 change 가 뜨게 비운다.
            event.target.value = ''
          }}
        />

        <div className="space-y-3">
          <Button variant="outline" onClick={() => picker.current?.click()} disabled={busy}>
            {busy && !shown ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <FileUp className="size-4" />
            )}
            {file ? `다른 파일 고르기 (지금: ${file.name})` : 'CSV 파일 고르기'}
          </Button>

          <ErrorNotice error={error} />

          {shown && (
            <>
              <p className="text-sm">
                {done ? (
                  <>
                    <b className="text-emerald-700 dark:text-emerald-500">
                      {done.created}개를 만들었습니다.
                    </b>{' '}
                    건너뜀 {done.skipped} · 오류 {done.errors}
                  </>
                ) : (
                  <>
                    <b>{shown.created}개를 만듭니다.</b> 건너뜀 {shown.skipped} · 오류{' '}
                    {shown.errors}
                  </>
                )}
              </p>

              <div className="max-h-80 space-y-1 overflow-y-auto rounded-md border p-2">
                {shown.rows.map((row) => (
                  <div key={row.line} className="flex items-start gap-2 text-xs">
                    <RowBadge row={row} />
                    <span className="min-w-0">
                      <span className="font-medium">{row.name}</span>{' '}
                      <span className="text-muted-foreground font-mono">({row.slug})</span>
                      {row.parent_slug && (
                        <span className="text-muted-foreground"> · 상위 {row.parent_slug}</span>
                      )}
                      {row.reason && (
                        <span className="text-muted-foreground block">
                          {row.line}행: {row.reason}
                        </span>
                      )}
                    </span>
                  </div>
                ))}
              </div>

              {!done && shown.errors > 0 && (
                <p className="text-xs text-amber-700 dark:text-amber-500">
                  오류 줄은 건너뛰고 나머지만 들어옵니다 — 무엇이 안 들어왔는지 위 목록이
                  말합니다. 파일을 손으로 고치지 말고, ReportArchive 쪽을 고쳐 다시
                  내보내는 편이 안전합니다.
                </p>
              )}
            </>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => {
              reset()
              onClose()
            }}
            disabled={busy}
          >
            {done ? '닫기' : '취소'}
          </Button>
          {!done && (
            <Button onClick={() => void run()} disabled={busy || !preview || preview.created === 0}>
              {busy && preview ? <Loader2 className="size-4 animate-spin" /> : null}
              {preview ? `${preview.created}개 가져오기` : '가져오기'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
