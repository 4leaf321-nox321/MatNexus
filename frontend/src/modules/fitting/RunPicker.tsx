/**
 * 이 카드에 **어느 시험을 쓸지** 고른다.
 *
 * ## 왜 필요한가
 *
 * 이상치 후보 둘을 빼고 8건으로 뽑은 것과, 10건 그대로 뽑은 것을 **나란히 두고
 * 견주는 것**이 실무의 정상 작업이다. 그런데 그 결정을 적을 자리가 없어서,
 * 지금까지는 시험의 **채택을 푸는 수밖에** 없었다. 그러면 통계 화면과 나중에
 * 만들 카드까지 전부 따라 바뀌어 두 장을 견줄 수가 없다.
 *
 * ## 이상치는 표시만 한다
 *
 * 통계 화면과 같은 규칙이다 — **아무것도 자동으로 버리지 않는다.** 후보에
 * 표를 달아 두고 빼는 것은 사람이 정한다. 자동으로 빼면 n 이 왜 그 수인지
 * 카드를 보는 사람이 알 수 없고, 그 판단이 어디에도 안 남는다.
 *
 * ## 기본은 전부다
 *
 * 아무것도 안 건드리면 전과 똑같이 채택된 전부로 만들어진다. 고르는 칸은
 * 더한 것이지 바꾼 것이 아니다.
 */

import { AlertTriangle } from 'lucide-react'

import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'

export interface RunChoice {
  id: string
  name: string
  /** 이상치 후보로 걸린 항목들. 비어 있으면 후보가 아니다. */
  flags: string[]
}

export function RunPicker({
  runs,
  used,
  onChange,
}: {
  runs: RunChoice[]
  /** 쓰기로 한 시험. **전부면 `null`** — 「고르지 않음」과 「전부 고름」은 같다. */
  used: string[] | null
  onChange: (next: string[] | null) => void
}) {
  const on = (id: string) => used === null || used.includes(id)
  const count = used === null ? runs.length : used.length
  const suspects = runs.filter((run) => run.flags.length > 0)

  function toggle(id: string) {
    const now = used === null ? runs.map((run) => run.id) : used
    const next = now.includes(id) ? now.filter((one) => one !== id) : [...now, id]
    // 전부 켜진 상태는 `null` 로 되돌린다 — 그래야 요청에 목록이 안 실리고,
    // 「고르지 않았다」 는 사실이 카드 근거에도 그대로 남는다.
    onChange(next.length === runs.length ? null : next)
  }

  if (runs.length === 0) return null

  return (
    <div className="rounded-md border p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">쓸 시험</span>
        <span className="text-muted-foreground text-xs tabular-nums">
          {count} / {runs.length}건
        </span>
        {used !== null && (
          <Button
            size="sm"
            variant="ghost"
            className="h-6 text-xs"
            onClick={() => onChange(null)}
          >
            전부 되돌리기
          </Button>
        )}
        {suspects.length > 0 && used === null && (
          // **한 번에 빼 주지 않는다.** 후보가 정말 이상치인지는 데이터가 아니라
          // 사람이 정한다 — 다만 하나씩 누르게 하면 열 건에서 일이 된다.
          <Button
            size="sm"
            variant="ghost"
            className="h-6 text-xs"
            onClick={() =>
              onChange(
                runs.filter((run) => run.flags.length === 0).map((run) => run.id)
              )
            }
          >
            이상치 후보 {suspects.length}건 빼기
          </Button>
        )}
      </div>

      <ul className="max-h-44 space-y-0.5 overflow-y-auto">
        {runs.map((run) => (
          <li key={run.id}>
            <label className="hover:bg-muted/40 flex items-center gap-2 rounded px-1 py-0.5">
              <input
                type="checkbox"
                aria-label={`${run.name} 쓰기`}
                checked={on(run.id)}
                onChange={() => toggle(run.id)}
              />
              <span className={`font-mono text-xs ${on(run.id) ? '' : 'opacity-40'}`}>
                {run.name}
              </span>
              {run.flags.length > 0 && (
                <Badge
                  variant="outline"
                  className="gap-1 text-[10px] text-amber-700 dark:text-amber-500"
                  title={`${run.flags.join(' · ')} 에서 이상치 후보입니다. 버려진 것이 아닙니다.`}
                >
                  <AlertTriangle className="size-3" />
                  {run.flags.join(' · ')}
                </Badge>
              )}
            </label>
          </li>
        ))}
      </ul>

      {used !== null && (
        <p className="text-muted-foreground mt-2 text-xs">
          <b>{runs.length - count}건을 뺐습니다.</b> 뺐다는 사실은 카드 근거에 남습니다 —
          채택은 그대로라 다른 카드·통계는 안 바뀝니다.
        </p>
      )}
    </div>
  )
}
