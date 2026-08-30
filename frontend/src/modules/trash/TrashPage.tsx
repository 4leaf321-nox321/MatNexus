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
 *
 * ## 여럿을 지울 때도 서버가 판단한다
 *
 * 골라서 한꺼번에 지우는 길은 **요청 하나**로 간다. 화면이 하나씩 부르면, 재료와
 * 그 아래 시료를 함께 골랐을 때 두 번째 요청이 「없는 행」 으로 터지고 **앞엣것은
 * 이미 지워져 되돌릴 수도 없다.** 겹친 선택을 푸는 것은 계층을 아는 쪽의 일이다.
 */

import { useState } from 'react'

import { TRASH_GROUPS, trashApi } from '@/modules/trash/api'
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
  // `종류-id` 를 열쇠로 든다 — 종류가 다르면 id 가 같을 수 있다.
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [purgingMany, setPurgingMany] = useState(false)

  const items = useResource(() => trashApi.list(kind ? { kind } : {}), [kind])
  const rows = items.data ?? []
  const labels = new Map(rows.map((row) => [row.kind, row.kind_label]))

  const keyOf = (row: TrashItem) => `${row.kind}-${row.id}`
  // **화면에 있는 것만 센다.** 걸러서 안 보이는 줄이 선택에 남아 있으면, 사람이
  // 본 수와 지워지는 수가 어긋난다.
  const chosen = rows.filter((row) => picked.has(keyOf(row)))

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

  /** 고른 것을 한 번에 지운다 — **요청 하나로.** 건너뛴 수는 서버가 세어 준다. */
  async function purgeChosen() {
    const targets = chosen.map((row) => ({ kind: row.kind, id: row.id }))
    setBusy('purge-many')
    setFailed(null)
    try {
      const done = await trashApi.purgeMany(targets)
      // **건너뛴 것을 말한다.** 다섯을 골랐는데 「셋 지움」 만 뜨면 나머지가 어떻게
      // 됐는지 사람이 모른다 — 겹쳐 고른 것은 사고가 아니라 정상이다.
      setSaid(
        done.skipped > 0
          ? `${done.purged}건을 지웠습니다 (${done.skipped}건은 함께 사라져 건너뜀) — ${done.said}`
          : `${done.purged}건을 지웠습니다 — ${done.said}`
      )
      setPicked(new Set())
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
        {/* **드롭다운이 아니라 토글이다.** 고를 것이 여덟이고 그중 무엇에
            지운 것이 있는지가 매번 다르다 — 드롭다운은 열어 봐야 목록을 알고,
            고르고 나면 나머지가 무엇이었는지 사라진다. 펼쳐 두면 **한눈에 보고
            한 번에 옮겨 다닌다.**

            두 묶음으로 갈라 세운다: 재료 계층은 아래로 딸린 것이 있고 수집
            체계는 정의 한 줄이 통째로 하나라, 되살릴 때 무슨 일이 나는지가
            다르다. */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2" role="group" aria-label="종류로 거르기">
          <Button
            size="sm"
            variant={kind === '' ? 'default' : 'outline'}
            className="h-7 text-xs"
            aria-pressed={kind === ''}
            onClick={() => {
              setKind('')
              setPicked(new Set())
            }}
          >
            전부
          </Button>
          {TRASH_GROUPS.map((group) => (
            <div key={group.label} className="flex items-center gap-1">
              <span className="text-muted-foreground text-[11px]">{group.label}</span>
              {group.kinds.map((one) => (
                <Button
                  key={one.key}
                  size="sm"
                  variant={kind === one.key ? 'default' : 'outline'}
                  className="h-7 text-xs"
                  aria-pressed={kind === one.key}
                  // **누른 것을 다시 누르면 전부로 돌아온다.** 토글은 끄는 길이
                  // 있어야 토글이다 — 없으면 「전부」 를 찾아 눈이 되돌아간다.
                  onClick={() => {
                    setKind((now) => (now === one.key ? '' : one.key))
                    setPicked(new Set())
                  }}
                >
                  {labels.get(one.key) ?? one.label}
                </Button>
              ))}
            </div>
          ))}
        </div>
      </div>

      {!items.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          {kind ? '그 종류로 지운 것이 없습니다.' : '지운 것이 없습니다.'}
        </div>
      )}

      {/* **고른 것이 있을 때만 뜬다.** 늘 떠 있으면 「0개 선택」 이라는 빈 줄이
          표 위를 차지하고, 실제로 고른 순간의 변화가 안 보인다. */}
      {chosen.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border bg-muted/40 px-3 py-2 text-sm">
          <span>
            <b>{chosen.length}건</b> 선택
          </span>
          <Button
            size="sm"
            variant="ghost"
            className="text-destructive h-7 text-xs"
            disabled={busy !== null}
            onClick={() => setPurgingMany(true)}
          >
            선택한 것 영구 삭제
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs"
            disabled={busy !== null}
            onClick={() => setPicked(new Set())}
          >
            선택 해제
          </Button>
        </div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <input
                    type="checkbox"
                    aria-label="이 쪽 전부 선택"
                    checked={rows.length > 0 && chosen.length === rows.length}
                    ref={(node) => {
                      if (node) {
                        node.indeterminate = chosen.length > 0 && chosen.length < rows.length
                      }
                    }}
                    onChange={(event) =>
                      setPicked(event.target.checked ? new Set(rows.map(keyOf)) : new Set())
                    }
                  />
                </TableHead>
                <TableHead className="whitespace-nowrap">언제 지웠나</TableHead>
                <TableHead>종류</TableHead>
                <TableHead>이름</TableHead>
                <TableHead>함께 지워진 것</TableHead>
                <TableHead className="text-right">할 일</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={keyOf(row)}>
                  <TableCell>
                    <input
                      type="checkbox"
                      aria-label={`${row.name || '이름 없음'} 선택`}
                      checked={picked.has(keyOf(row))}
                      onChange={(event) =>
                        setPicked((current) => {
                          const next = new Set(current)
                          if (event.target.checked) next.add(keyOf(row))
                          else next.delete(keyOf(row))
                          return next
                        })
                      }
                    />
                  </TableCell>
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

      {/* **고른 것을 이름으로 보여 준다.** 「5건을 지웁니다」 만으로는 어느 다섯인지
          모른다 — 옆줄을 잘못 눌렀을 수 있다. 많으면 앞의 몇을 보이고 나머지는 수로
          말한다. */}
      <ConfirmDialog
        open={purgingMany}
        title={`영구 삭제 ${chosen.length}건 — 되돌릴 수 없습니다`}
        confirmLabel={`${chosen.length}건 영구 삭제`}
        busy={busy !== null}
        body={
          <>
            <ul className="mb-2 list-disc space-y-0.5 pl-4">
              {chosen.slice(0, 8).map((row) => (
                <li key={keyOf(row)}>
                  <span className="text-muted-foreground">{row.kind_label}</span>{' '}
                  {row.name || '(이름 없음)'}
                  {below(row.below) && (
                    <span className="text-muted-foreground"> — 아래 {below(row.below)}</span>
                  )}
                </li>
              ))}
            </ul>
            {chosen.length > 8 && (
              <p className="text-muted-foreground mb-2">그 밖에 {chosen.length - 8}건</p>
            )}
            <p>
              행과 곡선 파일까지 <b>영영</b> 지웁니다. 휴지통에서도 사라지고 되살릴 수
              없습니다.
            </p>
            <p className="text-muted-foreground mt-1">
              위아래로 겹쳐 고른 것은 한 번에 사라집니다 — 재료를 지우면 그 아래 시료도
              함께 갑니다.
            </p>
          </>
        }
        onClose={() => setPurgingMany(false)}
        onConfirm={() => {
          setPurgingMany(false)
          void purgeChosen()
        }}
      />
    </div>
  )
}
