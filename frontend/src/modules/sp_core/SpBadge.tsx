/**
 * 「SP」 배지 — **이 값이 Standard Platform 의 무엇과 같은 것으로 이어져 있나**(ADR 0063).
 *
 * 기준정보 값 · 물성 · 물성군 · 분야 옆에 붙는다. 누르면 SP 쪽 이름 · key · 속성 · 관계와 누가
 * 언제 이었는지를 보인다. 전에는 이어도 변경 이력 말고는 어디에도 안 보였다(2026-11-02).
 *
 * ## 고치는 단추가 없다
 *
 * 잇고 끊는 일은 AI(MCP)가 후보를 보이고 사람이 확인한다 — 화면에도 잇는 길을 두면 「어디서
 * 잇나」 가 둘이 된다. **연결은 값을 바꾸지 않는다** — SP 이름이 달라도 MatNexus 의 값은
 * 그대로라는 것을 창 끝에 적는다. 안 적으면 「이었는데 왜 이름이 안 바뀌나」 를 묻게 된다.
 *
 * ## SP 에서 사라진 것에 이어져 있으면 붉게
 *
 * SP 가 지우거나 합친 객체에 이어진 연결은 낡은 것이다. 받기가 연결을 지우지 않으므로(사람의
 * 확인이라서) 배지가 그렇다고 말해야 다시 볼 사람이 생긴다.
 */

import { spCoreApi } from '@/modules/sp_core/api'
import type { SpLinked, SpRelation } from '@/modules/sp_core/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/components/ui/popover'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useResource } from '@/shared/hooks/useResource'
import { stamp, stampFull } from '@/shared/lib/datetime'
import { cn } from '@/shared/lib/utils'

/** 창에 보이는 속성 · 선의 수. 넘으면 몇 개 더 있는지만 말한다 — 전부는 AI 로 본다. */
const PROPS_SHOWN = 12
const EDGES_SHOWN = 8

export function SpBadge({
  links,
  label,
  className,
}: {
  /** 이 대상에 이어진 SP — 없으면 아무것도 안 그린다. */
  links: SpLinked[] | undefined
  /** 무엇의 배지인지 — 화면 읽기 도구가 읽는 이름. */
  label: string
  className?: string
}) {
  if (!links?.length) return null
  const stale = links.some((one) => one.sp_deleted)
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Badge
          asChild
          variant={stale ? 'destructive' : 'secondary'}
          className={cn('cursor-pointer align-middle', className)}
        >
          <button
            type="button"
            aria-label={`${label} — SP 연결 ${links.length}개${stale ? ' (SP 에서 사라진 것 있음)' : ''}`}
            title={
              stale
                ? 'SP 에서 사라진 객체에 이어져 있습니다 — 눌러서 확인'
                : 'Standard Platform 코어 온톨로지와 이어져 있습니다 — 눌러서 확인'
            }
          >
            SP{links.length > 1 ? ` ${links.length}` : ''}
          </button>
        </Badge>
      </PopoverTrigger>
      <PopoverContent className="max-h-[28rem] w-96 overflow-auto p-3" aria-label={`${label} SP 연결`}>
        <div className="space-y-3">
          {links.map((one) => (
            <SpObjectCard key={one.link_id} link={one} />
          ))}
        </div>
        <p className="text-muted-foreground mt-3 border-t pt-2 text-xs">
          연결은 「같은 것」 이라는 기록뿐이며 MatNexus 의 값은 바뀌지 않습니다. 잇기 · 끊기는
          AI(MCP)의 link_sp_core · unlink_sp_core 로 합니다.
        </p>
      </PopoverContent>
    </Popover>
  )
}

/** 이어진 SP 객체 하나 — 창이 열릴 때 받는다. */
function SpObjectCard({ link }: { link: SpLinked }) {
  const detail = useResource(
    () => spCoreApi.object(link.sp_type, link.sp_key),
    [link.sp_type, link.sp_key]
  )
  const data = detail.data
  const mine = data?.links.find((one) => one.id === link.link_id)
  const properties = Object.entries(data?.properties ?? {})
  const edges = [
    ...(data?.outgoing ?? []).filter((one) => !one.deleted).map((one) => ({ one, out: true })),
    ...(data?.incoming ?? []).filter((one) => !one.deleted).map((one) => ({ one, out: false })),
  ]

  return (
    <section className="space-y-1.5 text-sm">
      <p className="text-muted-foreground text-xs">{link.sp_type_label ?? link.sp_type}</p>
      <p className="font-medium">
        {link.sp_label ?? link.sp_key}{' '}
        <code className="text-muted-foreground font-mono text-xs font-normal">{link.sp_key}</code>
      </p>
      {link.sp_deleted && (
        <p className="text-destructive text-xs">
          SP 에서 사라진 객체입니다
          {data?.merged_into ? ` — ${data.merged_into} 에 합쳐졌습니다` : ''}. 연결을 다시 봐야
          합니다.
        </p>
      )}

      <ErrorNotice error={detail.error} />
      {detail.loading && !data ? (
        <Skeleton className="h-16" />
      ) : (
        data && (
          <>
            {properties.length > 0 && (
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                {properties.slice(0, PROPS_SHOWN).map(([key, value]) => (
                  <div key={key} className="contents">
                    <dt className="text-muted-foreground">{key}</dt>
                    <dd className="break-all">{shown(value)}</dd>
                  </div>
                ))}
              </dl>
            )}
            {properties.length > PROPS_SHOWN && (
              <p className="text-muted-foreground text-xs">속성 {properties.length - PROPS_SHOWN}개 더</p>
            )}
            {edges.length > 0 && (
              <ul className="space-y-0.5 text-xs">
                {edges.slice(0, EDGES_SHOWN).map(({ one, out }) => (
                  <li key={`${out ? '>' : '<'}${one.relation}:${out ? one.dst : one.src}`}>
                    <Edge relation={one} out={out} />
                  </li>
                ))}
              </ul>
            )}
            {edges.length > EDGES_SHOWN && (
              <p className="text-muted-foreground text-xs">관계 {edges.length - EDGES_SHOWN}개 더</p>
            )}
            {mine && (
              <p className="text-muted-foreground text-xs" title={stampFull(mine.created_at)}>
                {mine.created_by ?? '누군가'} · {stamp(mine.created_at)} 연결
                {mine.note ? ` — ${mine.note}` : ''}
              </p>
            )}
          </>
        )
      )}
    </section>
  )
}

/** 선 하나 — 「→ 관계 맞은편」 꼴. 맞은편 이름을 못 찾으면 key 를 보인다. */
function Edge({ relation, out }: { relation: SpRelation; out: boolean }) {
  const other = out
    ? (relation.dst_label ?? relation.dst)
    : (relation.src_label ?? relation.src)
  const otherType = out ? relation.dst_type : relation.src_type
  return (
    <span>
      <span className="text-muted-foreground">{out ? '→' : '←'}</span> {relation.relation}{' '}
      <span className="font-medium">{other}</span>{' '}
      <span className="text-muted-foreground">({otherType})</span>
    </span>
  )
}

/** 속성 값 한 칸. 묶음 값은 줄여 적는다 — 창이 한 값 때문에 넓어지지 않게. */
function shown(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') {
    const text = JSON.stringify(value)
    return text.length > 80 ? `${text.slice(0, 80)}…` : text
  }
  return String(value)
}
