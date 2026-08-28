/**
 * 홈 요약 — **일이 남은 곳부터 보인다.**
 *
 * 홈은 4단계 안내 카드였다. 처음 오는 사람에게는 좋은데, **매일 오는 사람에게는
 * 매번 같은 화면**이다 — 안내는 한 번 읽으면 끝인데 자리는 계속 차지한다.
 *
 * 개발 DB 로 재 보니 드러난 것 셋.
 *
 *     물성 카드 11        확정 1 · 초안 10   ← 승인 안 받은 것이 열이다
 *     카드 있는 재료 5/94                     ← 94개 중 89개가 카드 없음
 *     처리 대기 71                            ← 읽혔는데 채택이 없는 시험
 *
 * 합쳐 놓으면 「카드 11」로만 보이는 것들이다.
 *
 * ## 0 은 안 보인다
 *
 * 파싱 실패 0건을 「0」으로 그리면 **그것도 상태처럼 읽힌다.** 막힌 것이 없으면
 * 그 줄이 통째로 사라져야 "지금 막힌 게 없다" 가 한눈에 온다.
 */

import { Link } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'

import type { Overview } from '@/modules/statistics/api'
import { Badge } from '@/shared/components/ui/badge'
import { Skeleton } from '@/shared/components/ui/skeleton'

export function OverviewPanel({
  data,
  loading,
  workspaceSlug,
}: {
  data: Overview | null
  loading: boolean
  workspaceSlug: string
}) {
  if (loading && !data) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((index) => (
          <Skeleton key={index} className="h-24" />
        ))}
      </div>
    )
  }
  if (!data) return null

  const covered = data.material_count
    ? Math.round((data.materials_with_card / data.material_count) * 100)
    : 0

  return (
    <div className="space-y-3">
      {/* **막힌 것부터.** 0 이면 그 줄이 통째로 사라진다 — 0을 그리면 그것도
          상태처럼 읽히고, "지금 막힌 게 없다" 가 한눈에 안 온다. */}
      {(data.waiting_to_process > 0 || data.parse_failed > 0 || data.card_draft > 0) && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm dark:border-amber-900 dark:bg-amber-950/40">
          <AlertTriangle className="size-4 shrink-0 text-amber-600 dark:text-amber-500" />
          <span className="text-muted-foreground text-xs">남은 일</span>
          {data.parse_failed > 0 && (
            <Pending to={`/w/${workspaceSlug}/tests?status=failed`}>
              읽기 실패 {data.parse_failed}
            </Pending>
          )}
          {data.waiting_to_process > 0 && (
            <Pending to={`/w/${workspaceSlug}/tests`}>처리 대기 {data.waiting_to_process}</Pending>
          )}
          {data.card_draft > 0 && (
            <Pending to="/materials">
              {/* **확정 안 된 카드는 "이 값으로 해석이 돌 수 있다" 는 승인을
                  못 받은 것이다.** 홈에 없으면 아무도 안 본다. */}
              확정 대기 {data.card_draft}
            </Pending>
          )}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label="재료" value={data.material_count} to="/materials">
          <Split items={data.families} />
        </Tile>

        <Tile label="시험" value={data.run_count} to={`/w/${workspaceSlug}/tests`}>
          <Split items={data.test_types} />
        </Tile>

        <Tile label="시료 · 시편" value={`${data.sample_count} · ${data.specimen_count}`} />

        <Tile label="물성 카드" value={data.card_total}>
          <div className="mt-1 flex flex-wrap gap-1">
            {data.card_published > 0 && (
              <Badge variant="secondary" className="text-[11px]">
                확정 {data.card_published}
              </Badge>
            )}
            {data.card_draft > 0 && (
              <Badge variant="outline" className="text-[11px]">
                초안 {data.card_draft}
              </Badge>
            )}
            {data.card_deprecated > 0 && (
              <Badge variant="outline" className="text-[11px]">
                내림 {data.card_deprecated}
              </Badge>
            )}
          </div>
          {/* **덮인 정도.** 카드 수만 보면 많아 보이는데, 재료 94개 중 5개라는
              사실이 진짜 상태다. */}
          {data.material_count > 0 && (
            <p className="text-muted-foreground mt-1 text-[11px]">
              재료 {data.materials_with_card}/{data.material_count} 에 있음 ({covered}%)
            </p>
          )}
        </Tile>
      </div>
    </div>
  )
}

function Pending({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      className="rounded border border-amber-400 bg-background px-2 py-0.5 text-xs font-medium hover:bg-amber-100 dark:border-amber-800 dark:hover:bg-amber-900/40"
    >
      {children}
    </Link>
  )
}

function Tile({
  label,
  value,
  to,
  children,
}: {
  label: string
  value: number | string
  to?: string
  children?: React.ReactNode
}) {
  const body = (
    <>
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="mt-0.5 text-2xl font-semibold tabular-nums">{value}</p>
      {children}
    </>
  )
  return to ? (
    <Link to={to} className="hover:bg-muted/50 rounded-md border p-3">
      {body}
    </Link>
  ) : (
    <div className="rounded-md border p-3">{body}</div>
  )
}

/**
 * 분포 한 줄. **잘못 만든 것이 여기서 드러난다** — 개발 DB 에 `Family` 라는
 * 재료군의 재료가 1건 있었고, 요약을 만들고 나서야 보였다.
 *
 * 셋까지만 적고 나머지는 수로 접는다. 분류가 늘면 줄이 무너진다.
 */
function Split({ items }: { items: { label: string; count: number }[] }) {
  if (items.length === 0) return null
  const shown = items.slice(0, 3)
  const rest = items.length - shown.length
  return (
    <p className="text-muted-foreground mt-1 truncate text-[11px]">
      {shown.map((item) => `${item.label} ${item.count}`).join(' · ')}
      {rest > 0 && ` 외 ${rest}`}
    </p>
  )
}
