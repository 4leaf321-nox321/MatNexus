/**
 * 물성 카드 — **재료를 거치지 않고 찾는다.**
 *
 * 지금까지 카드에 닿는 길은 재료 상세의 'CAE 카드' 탭뿐이었다. 재료를 알면 두
 * 번에 닿지만, *"지난주에 만든 그 카드가 어느 재료였더라"* 를 물으면 재료를
 * 전부 뒤져야 했다.
 *
 * ## 거르는 일은 서버가 한다
 *
 * 앞 50장만 받아 화면에서 거르면 **뒤엣것이 없는 카드가 된다** — 재료 목록
 * 패널이 같은 이유로 그렇게 되어 있다. 검색도 마찬가지다.
 *
 * ## 잘렸으면 잘렸다고 적는다
 *
 * 「43장 중 50장」. 표시 없이 자르면 사람이 알 방법이 없고, 그러면 없는 카드를
 * 없다고 믿는다.
 *
 * ## 여러 장을 골라 한 묶음으로 (v1.168.0)
 *
 * 해석 하나에 재료가 여럿 들어간다. 한 장씩 받아 사람이 폴더에 모으면 **그 묶음이
 * 무엇이었는지가 아무 데도 안 남는다.** 골라서 `manifest.json`·`SHA256SUMS` 와 함께
 * 내보낸다(ADR 0024 ②) — 받은 쪽이 「그때 그 카드가 맞나」 를 검산할 수 있다.
 */

import { AlertTriangle, Globe2, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { BundleBar } from '@/modules/fitting/BundleBar'
import { CardFilterPanel } from '@/modules/fitting/CardFilterPanel'
import { ExportMenu } from '@/modules/fitting/ExportMenu'
import { STATUS_LABELS, fittingApi } from '@/modules/fitting/api'
import type { PropertyCard } from '@/modules/fitting/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { useResource } from '@/shared/hooks/useResource'

/** 한 번에 받는 수. 서버 상한(200)보다 작게 둔다 — 화면이 읽을 수 있는 만큼이다. */
const PAGE = 50

export default function CardsPage() {
  const [status, setStatus] = useState<string | null>(null)
  const [testType, setTestType] = useState<string | null>(null)
  const [owner, setOwner] = useState<string | null>(null)
  const [typed, setTyped] = useState('')
  const [q, setQ] = useState('')
  const [limit, setLimit] = useState(PAGE)
  const [error, setError] = useState<Error | null>(null)
  /** 묶음에 담을 카드. **거르기를 바꿔도 안 비운다** — 조건을 바꿔 가며 모으는
   *  것이 이 화면에서 카드를 고르는 방식이다. */
  const [picked, setPicked] = useState<Set<string>>(new Set())

  // 타이핑이 멎으면 묻는다. 글자마다 부르면 앞 글자의 응답이 뒤늦게 와서
  // 목록을 덮는 일이 생긴다.
  useEffect(() => {
    const timer = setTimeout(() => setQ(typed.trim()), 300)
    return () => clearTimeout(timer)
  }, [typed])

  // 필터가 바뀌면 처음부터 다시 본다. **안 그러면 2쪽을 보던 사람이 필터를
  // 걸었을 때 빈 화면을 본다.**
  useEffect(() => {
    setLimit(PAGE)
  }, [status, testType, owner, q])

  const page = useResource(
    () =>
      fittingApi.cards({
        status: status ?? undefined,
        test_type_key: testType ?? undefined,
        owner: owner ?? undefined,
        q: q || undefined,
        limit,
      }),
    [status, testType, owner, q, limit]
  )
  // **거르기 목록은 필터와 함께 안 바뀐다.** 「무엇이 있나」를 답하는 자리라
  // 한 번만 읽는다.
  const facets = useResource(() => fittingApi.cardFacets(), [])
  const formats = useResource(() => fittingApi.formats(), [])

  const rows = useMemo(() => page.data?.items ?? [], [page.data])
  const total = page.data?.total ?? 0

  return (
    <section>
      <CardFilterPanel
        facets={facets.data ?? null}
        status={status}
        testType={testType}
        owner={owner}
        onPickStatus={setStatus}
        onPickTestType={setTestType}
        onPickOwner={setOwner}
      />

      <PageHeader
        title="물성 카드"
        description="확정한 물성 한 벌입니다. 여기서 바로 솔버 덱으로 내보냅니다."
      />

      <div className="mb-4 flex items-center gap-2">
        <div className="relative w-80">
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input
            className="pl-8"
            value={typed}
            placeholder="재료 이름 · 카드 이름"
            aria-label="카드 검색"
            onChange={(event) => setTyped(event.target.value)}
          />
        </div>
        <span className="text-muted-foreground text-sm">
          {page.loading ? '찾는 중…' : `${total}장`}
        </span>
      </div>

      <ErrorNotice error={page.error ?? facets.error ?? error} className="mb-4" />

      {!page.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          조건에 맞는 카드가 없습니다. 카드는 재료 상세의 <b>CAE 카드</b> 탭에서 만듭니다.
        </div>
      )}

      <div className="space-y-2">
        {rows.map((card) => (
          <Row
            key={card.id}
            card={card}
            formats={formats.data ?? []}
            onError={setError}
            picked={picked.has(card.id)}
            onPick={(next) =>
              setPicked((now) => {
                const copy = new Set(now)
                if (next) copy.add(card.id)
                else copy.delete(card.id)
                return copy
              })
            }
          />
        ))}
      </div>

      <BundleBar
        ids={[...picked]}
        formats={formats.data ?? []}
        onClear={() => setPicked(new Set())}
        onError={setError}
      />

      {/* **조용히 자르지 않는다.** 표시 없이 자르면 없는 카드를 없다고 믿는다. */}
      {rows.length < total && (
        <div className="mt-4 flex items-center gap-3">
          <Button variant="outline" onClick={() => setLimit(limit + PAGE)}>
            더 보기
          </Button>
          <span className="text-muted-foreground text-sm">
            {total}장 중 {rows.length}장을 보고 있습니다.
          </span>
        </div>
      )}
    </section>
  )
}

function Row({
  card,
  formats,
  onError,
  picked,
  onPick,
}: {
  card: PropertyCard
  formats: Parameters<typeof ExportMenu>[0]['formats']
  onError: (error: Error) => void
  picked: boolean
  onPick: (next: boolean) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border p-3">
      {/* **낱장 내보내기를 없애지 않는다.** 한 장만 필요한 사람이 더 많고,
          묶음은 여럿을 고를 때만 뜬다. */}
      <input
        type="checkbox"
        aria-label={`${card.label} 묶음에 담기`}
        checked={picked}
        onChange={(event) => onPick(event.target.checked)}
      />
      <span className="font-medium">{card.label}</span>
      <Badge
        variant={
          card.status === 'published'
            ? 'default'
            : card.status === 'deprecated'
              ? 'outline'
              : 'secondary'
        }
      >
        {STATUS_LABELS[card.status] ?? card.status}
      </Badge>

      {/* **어느 재료의 것인지가 이 화면의 존재 이유다.** 누르면 그 재료로 간다. */}
      <Link
        to={`/materials/${card.material_id}`}
        className="text-sm underline-offset-2 hover:underline"
      >
        {card.material_name}
      </Link>

      {card.is_global && (
        <Globe2 className="text-muted-foreground size-3.5" aria-label="전역" />
      )}
      {!card.is_global && card.owner_workspace_name && (
        <span className="text-muted-foreground text-xs">{card.owner_workspace_name}</span>
      )}

      <span className="text-muted-foreground text-sm">
        {/* **시험에서 나온 카드와 같은 모양으로 그리면 안 된다.** 시험종류가
            비어 있으면 `· · 시편 0개` 로 보이는데, 그것은 "시험이 지워졌다" 로
            읽힌다(ADR 0016). */}
        {card.test_type_key === null ? (
          <span className="text-amber-700 dark:text-amber-500">시험 없음 · 적어 둔 값</span>
        ) : (
          <>
            {card.test_type_key} · {card.orientation} · 시편{' '}
            {String(card.source.sample_count ?? '?')}개
          </>
        )}
      </span>

      <span className="text-muted-foreground text-xs">
        {new Date(card.created_at).toLocaleDateString('ko-KR')}
      </span>

      {/* **못 쓰게 된 카드를 짚는다.** 만든 계산이 지금 코드에 없으면 내보내기가
          막힌다 — 전역 목록이야말로 "그런 카드가 몇 장인가" 를 처음 물을 수
          있는 자리다. */}
      {card.problem && (
        <span className="text-destructive flex items-center gap-1 text-xs" title={card.problem}>
          <AlertTriangle className="size-3.5" />
          풀 수 없음
        </span>
      )}

      <div className="ml-auto">
        <ExportMenu card={card} formats={formats} onError={onError} />
      </div>
    </div>
  )
}
