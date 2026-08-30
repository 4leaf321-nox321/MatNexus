/**
 * 물성 정의 파일 들여오기 — **무엇이 들어오는지 보고 누른다.**
 *
 * ## 왜 창이 하나 더 있나
 *
 * 파일을 고르자마자 넣으면, 개발 서버에서 만든 정의가 **운영의 같은 key 를 말없이
 * 덮는다.** 그리고 덮인 정의로 다음에 뽑는 덱이 달라지는데, 그때 그것을 되돌릴
 * 근거가 아무 데도 없다 — 파일은 사람의 컴퓨터에 있고 서버에는 흔적이 없다.
 *
 * 그래서 넣기 전에 **한 줄씩 지금 서버의 상태와 맞춰 보인다**: 새로 만드는 것인가,
 * 이미 있는 것인가. 이미 있는 것은 **기본이 건너뛰기**다 — 덮는 것은 사람이
 * 한 줄씩 켜야 한다.
 *
 * ## 소유는 안 옮긴다
 *
 * 파일에 부서가 없다(`profileFile.ts`). 들여온 정의는 **들여온 사람의 부서**로
 * 간다. 전역으로 올리는 것은 성격이 다른 결정이라 그 자리에서 따로 한다.
 */

import { useState } from 'react'
import { AlertTriangle, Check, Loader2 } from 'lucide-react'

import { fittingApi } from '@/modules/fitting/api'
import type { ProfileInFile } from '@/modules/fitting/profileFile'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'

interface Props {
  /** 파일에서 읽은 정의. 비면 창이 안 뜬다. */
  incoming: ProfileInFile[] | null
  /** 지금 이 서버에 있는 key — 겹치는지 보려고. */
  existing: Set<string>
  onClose: () => void
  onDone: (said: string) => void
}

export function ImportProfilesDialog({ incoming, existing, onClose, onDone }: Props) {
  /** 덮어쓸 key. **기본은 비어 있다** — 덮는 것은 한 줄씩 켠다. */
  const [overwrite, setOverwrite] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<string[]>([])

  if (!incoming) return null

  const fresh = incoming.filter((one) => !existing.has(one.key))
  const clashing = incoming.filter((one) => existing.has(one.key))
  const willWrite = fresh.length + overwrite.size

  async function apply() {
    if (!incoming) return
    setBusy(true)
    setFailed([])
    const problems: string[] = []
    let made = 0
    let replaced = 0

    // **한 벌씩 넣는다.** 하나가 막혀도 나머지는 들어가는 편이 낫다 — 열 개 중
    // 하나가 코드 렌더러와 이름이 겹쳤다고 아홉을 다시 고르게 하지 않는다.
    // 대신 무엇이 안 들어갔는지 이름으로 말한다.
    for (const one of incoming) {
      const already = existing.has(one.key)
      if (already && !overwrite.has(one.key)) continue
      const payload = {
        label: one.label,
        description: one.description,
        definition: one.definition,
        is_active: one.is_active,
      }
      try {
        if (already) {
          await fittingApi.saveExportProfile(one.key, payload)
          replaced += 1
        } else {
          await fittingApi.createExportProfile({ ...payload, key: one.key })
          made += 1
        }
      } catch (caught) {
        problems.push(
          `${one.key} — ${caught instanceof Error ? caught.message : '넣지 못했습니다.'}`
        )
      }
    }

    setBusy(false)
    if (problems.length > 0) {
      setFailed(problems)
      // **닫지 않는다.** 무엇이 안 들어갔는지 읽을 자리가 사라지면 안 된다.
      return
    }
    const parts = []
    if (made) parts.push(`${made}건 만듦`)
    if (replaced) parts.push(`${replaced}건 덮음`)
    const skipped = incoming.length - made - replaced
    if (skipped) parts.push(`${skipped}건 건너뜀`)
    onDone(parts.join(' · ') || '바뀐 것 없음')
  }

  return (
    <Dialog open onOpenChange={(open) => (open ? null : onClose())}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>물성 정의 들여오기 — {incoming.length}건</DialogTitle>
          <DialogDescription>
            들여온 정의는 <b>내 부서의 것</b>이 됩니다. 파일에는 부서가 실리지 않습니다 —
            개발 서버의 부서를 운영에 그대로 옮기면 남의 부서 것이 됩니다.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-80 space-y-1 overflow-y-auto">
          {incoming.map((one) => {
            const already = existing.has(one.key)
            const on = overwrite.has(one.key)
            return (
              <div
                key={one.key}
                className="flex items-start gap-3 rounded border px-3 py-2 text-sm"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate">
                    <span className="font-mono text-xs">{one.key}</span> — {one.label}
                  </p>
                  {one.description ? (
                    <p className="text-muted-foreground truncate text-xs">{one.description}</p>
                  ) : null}
                </div>
                {already ? (
                  <label className="flex shrink-0 items-center gap-1.5 text-xs">
                    <input
                      type="checkbox"
                      aria-label={`${one.key} 덮어쓰기`}
                      checked={on}
                      disabled={busy}
                      onChange={(event) =>
                        setOverwrite((current) => {
                          const next = new Set(current)
                          if (event.target.checked) next.add(one.key)
                          else next.delete(one.key)
                          return next
                        })
                      }
                    />
                    <span className={on ? 'text-destructive' : 'text-muted-foreground'}>
                      이미 있음 — 덮어쓰기
                    </span>
                  </label>
                ) : (
                  <span className="text-muted-foreground flex shrink-0 items-center gap-1 text-xs">
                    <Check className="size-3.5" />새 정의
                  </span>
                )}
              </div>
            )
          })}
        </div>

        {clashing.length > 0 && overwrite.size > 0 ? (
          <p className="text-destructive flex items-start gap-1.5 text-xs">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            덮어쓴 정의로 <b>다음에 뽑는 덱이 달라집니다.</b> 이미 내보낸 덱 파일은
            그대로입니다.
          </p>
        ) : null}

        {failed.length > 0 ? (
          <div className="text-destructive space-y-1 rounded border border-current/30 p-2 text-xs">
            <p className="font-medium">{failed.length}건이 안 들어갔습니다.</p>
            {failed.map((one) => (
              <p key={one}>{one}</p>
            ))}
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={() => void apply()} disabled={busy || willWrite === 0}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : null}
            {willWrite === 0 ? '넣을 것이 없습니다' : `${willWrite}건 넣기`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
