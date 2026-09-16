/**
 * ReportArchive 부서 트리 가져오기 — **계획을 보고 누른다.**
 *
 * 조직도는 한 번 잘못 들어가면 지우기 어렵다(부서마다 재료·시험이 매달리기
 * 시작한다). 그래서 CSV 를 넣어도 **바로 만들지 않고** 무엇이 만들어질지 먼저
 * 보여 준다 — 만들 것·건너뛸 것·오류를 줄마다.
 *
 * 넣는 자리는 **붙여넣기 칸 하나**다(TestScope 와 같은 모양). ReportArchive 가
 * 내보낸 파일은 「파일에서 읽기」 로 그 칸을 채운다 — 파일이 곧 입력이면 스프레드
 * 시트에서 몇 줄만 복사해 오거나, 다른 PC 에서 받은 내용을 메신저로 건네받았을 때
 * 파일로 저장부터 해야 한다.
 *
 * 오류가 있어도 **막지 않는다.** TF 아래 행 하나 때문에 부서 마흔 개를 못 들여오면
 * 사람은 파일을 손으로 고치기 시작하고, 고친 파일은 원본과 갈린다. 오류 줄은
 * 남겨 두고 되는 것만 들여온다 — 무엇이 안 들어왔는지는 결과가 말한다.
 */

import { FileUp, Loader2, Search } from 'lucide-react'
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
import { Textarea } from '@/shared/components/ui/textarea'

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
  const [text, setText] = useState('')
  const [preview, setPreview] = useState<WorkspaceImportResult | null>(null)
  const [done, setDone] = useState<WorkspaceImportResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  function reset() {
    setText('')
    setPreview(null)
    setDone(null)
    setError(null)
  }

  /** 글자가 바뀌면 계획은 옛것이다 — 지우고 다시 보게 한다. */
  function edit(next: string) {
    setText(next)
    setPreview(null)
    setDone(null)
    setError(null)
  }

  async function plan(source = text) {
    if (!source.trim()) return
    setPreview(null)
    setDone(null)
    setError(null)
    setBusy(true)
    try {
      setPreview(await workspacesApi.previewImport(source))
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('CSV 를 읽지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  /** 파일은 칸을 채우는 수단이다 — 읽어 넣고 바로 계획을 보여 준다. */
  async function readFile(file: File) {
    let content: string
    try {
      content = await file.text()
    } catch {
      setError(new Error('파일을 읽지 못했습니다.'))
      return
    }
    setText(content)
    await plan(content)
  }

  async function run() {
    if (!text.trim()) return
    setBusy(true)
    setError(null)
    try {
      setDone(await workspacesApi.runImport(text))
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
            ReportArchive 의 시스템 관리 &gt; 「부서 정보 내보내기」 가 만든 CSV(부서정보.csv)
            내용을 붙여 넣거나 파일에서 읽습니다. 이미 있는 부서는 건드리지 않습니다 — 새로
            생긴 부서만 들어옵니다.
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
            if (next) void readFile(next)
            // 같은 파일을 다시 골라도 change 가 뜨게 비운다.
            event.target.value = ''
          }}
        />

        <div className="space-y-3">
          <Textarea
            aria-label="부서 정보 CSV"
            placeholder={'slug,name,parent_slug,kind\nrnd,연구소,,org\nrnd-poly,고분자팀,rnd,org'}
            value={text}
            onChange={(event) => edit(event.target.value)}
            disabled={busy || done !== null}
            className="min-h-40 font-mono text-xs"
            spellCheck={false}
          />

          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => picker.current?.click()}
              disabled={busy || done !== null}
            >
              <FileUp className="size-4" />
              파일에서 읽기
            </Button>
            {!done && (
              <Button
                variant="outline"
                onClick={() => void plan()}
                disabled={busy || !text.trim() || preview !== null}
              >
                {busy && !preview ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Search className="size-4" />
                )}
                미리보기
              </Button>
            )}
          </div>

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
                  말합니다. 여기서 글자를 고치지 말고, ReportArchive 쪽을 고쳐 다시
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
