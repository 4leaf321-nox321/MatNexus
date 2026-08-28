/**
 * 휴지통 — **지운 것이 어디로 갔는지.**
 *
 * ## 왜 만들었나
 *
 * 삭제가 소프트라 행은 남는데 **볼 자리가 없었다.** 그래서 지운 것은 "사라진 것"
 * 도 "남은 것" 도 아닌 상태였고, 실제로 사고가 났다(2026-08-28): 이관에서 금속
 * 재료를 지운 뒤 같은 이름으로 다시 넣으려다 전부 막혔는데, 막고 있던 그 행이
 * **화면 어디에도 없어서** 이유를 알 방법이 없었다.
 *
 * 유니크는 부분 인덱스로 고쳤다(v1.126.0). 그건 **막히지 않게** 한 것이고,
 * 이 화면은 **보이게** 하는 나머지다.
 *
 * ## 판단을 화면이 하지 않는다
 *
 * 되살릴 수 있는지도, 아래에 무엇이 딸렸는지도 서버가 실어 준다. 화면이 스스로
 * 세면 사람이 본 숫자와 실제로 돌아오는 것이 어긋나고, 그러면 사람이 누른
 * 「예」 는 다른 것에 대한 대답이 된다.
 *
 * ## 못 하는 이유를 적는다
 *
 * 되살릴 수 없을 때 단추를 그냥 끄지 않는다. **왜 안 되는지와 무엇을 먼저 해야
 * 하는지**를 그 자리에 적는다 — 처리 화면이 「돌려 보기가 그냥 비활성」 이었을
 * 때 사람들이 거기서 멈췄다.
 */

import { useState } from 'react'

import { TRASH_KINDS, trashApi } from '@/modules/trash/api'
import type { TrashItem } from '@/modules/trash/api'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'
import { stamp } from '@/shared/lib/datetime'

/** `{시료: 2, 시편: 6}` → `시료 2건 · 시편 6건`. 비면 빈 글자. */
function below(counts: Record<string, number>): string {
  return Object.entries(counts)
    .filter(([, count]) => count > 0)
    .map(([label, count]) => `${label} ${count}건`)
    .join(' · ')
}

export default function TrashPage() {
  const [kind, setKind] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [said, setSaid] = useState<string | null>(null)
  const [failed, setFailed] = useState<Error | null>(null)
  const [purging, setPurging] = useState<TrashItem | null>(null)

  const items = useResource(() => trashApi.list(kind ? { kind } : {}), [kind])
  const rows = items.data ?? []
  const labels = new Map(rows.map((row) => [row.kind, row.kind_label]))

  async function run(job: () => Promise<{ said: string }>, what: string) {
    setBusy(what)
    setFailed(null)
    try {
      const done = await job()
      setSaid(done.said)
      items.reload()
    } catch (error) {
      setFailed(error as Error)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="휴지통"
        description="지운 재료·시료·시편·시험입니다. 삭제는 행을 남기므로 되살릴 수 있습니다 — 다만 영구 삭제는 되돌릴 수 없습니다."
      />

      <ErrorNotice error={failed ?? items.error} />

      {said && (
        <div className="rounded-md border border-emerald-500/40 bg-emerald-500/5 p-3 text-sm">
          끝났습니다 — <b>{said}</b>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">종류</span>
        <select
          aria-label="종류로 거르기"
          className="border-input bg-background h-8 rounded-md border px-2 text-sm"
          value={kind}
          onChange={(event) => setKind(event.target.value)}
        >
          <option value="">전부</option>
          {TRASH_KINDS.map((one) => (
            <option key={one} value={one}>
              {labels.get(one) ?? one}
            </option>
          ))}
        </select>
      </div>

      {!items.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          {kind ? '그 종류로 지운 것이 없습니다.' : '지운 것이 없습니다.'}
        </div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="whitespace-nowrap">언제 지웠나</TableHead>
                <TableHead>종류</TableHead>
                <TableHead>이름</TableHead>
                <TableHead>함께 지워진 것</TableHead>
                <TableHead className="text-right">할 일</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={`${row.kind}-${row.id}`}>
                  <TableCell className="text-muted-foreground text-xs whitespace-nowrap tabular-nums">
                    {stamp(row.deleted_at)}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{row.kind_label}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="text-sm">{row.name || '(이름 없음)'}</div>
                    {/* **못 되살리는 이유를 여기 적는다.** 단추만 꺼 두면 사람은
                        그 자리에서 멈춘다. */}
                    {row.blocked && (
                      <p className="mt-0.5 text-xs text-amber-700 dark:text-amber-500">
                        {row.blocked}
                      </p>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {below(row.below) || '—'}
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <Button
                      size="sm"
                      variant="secondary"
                      className="h-7 text-xs"
                      disabled={!!row.blocked || busy !== null}
                      onClick={() =>
                        run(() => trashApi.restore(row.kind, row.id), `restore-${row.id}`)
                      }
                    >
                      {busy === `restore-${row.id}` ? '되살리는 중…' : '되살리기'}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive ml-1 h-7 text-xs"
                      disabled={busy !== null}
                      onClick={() => setPurging(row)}
                    >
                      영구 삭제
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* **무엇이 사라지는지 이름과 수로 적는다.** 「정말 지울까요?」 만으로는
          사람이 무엇에 동의하는지 모른다. */}
      <ConfirmDialog
        open={purging !== null}
        title="영구 삭제 — 되돌릴 수 없습니다"
        confirmLabel="영구 삭제"
        busy={busy !== null}
        body={
          purging && (
            <>
              <b>
                {purging.kind_label} {purging.name || '(이름 없음)'}
              </b>
              {below(purging.below) && <> 와 그 아래 {below(purging.below)}</>} 를 행과
              곡선 파일까지 <b>영영</b> 지웁니다. 휴지통에서도 사라지고 되살릴 수 없습니다.
            </>
          )
        }
        onClose={() => setPurging(null)}
        onConfirm={() => {
          const target = purging
          if (!target) return
          setPurging(null)
          void run(() => trashApi.purge(target.kind, target.id), `purge-${target.id}`)
        }}
      />
    </div>
  )
}
