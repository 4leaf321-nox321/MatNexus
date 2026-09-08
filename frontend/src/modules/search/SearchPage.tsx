/**
 * 전체 검색 — **한 칸에 치면 무엇이든 찾는다.**
 *
 * 여태 검색 칸은 화면마다 따로 있었다. 그래서 「SECC180」 이 재료인지 시료인지
 * 시험 이름인지 아는 사람만 찾을 수 있었다 — 모르면 화면 넷을 돌아야 했다.
 *
 * ## 모드 셋을 사람 말로 보여 준다
 *
 *     일치     정확히 그 이름
 *     포함     그 말이 들어간 것 (기본)
 *     비슷     오타·표기 흔들림까지
 *
 * **왜 걸렸는지를 결과마다 적는다.** 「비슷」 으로 뜬 것에 이유가 없으면 엉뚱한
 * 결과로 읽힌다 — 「secc 180」 을 쳤는데 「SECC_MDOI」 가 나온 것은 맞는 동작이고,
 * 그것을 화면이 말해 줘야 한다.
 *
 * ## 주소가 곧 검색이다
 *
 * `?q=...&mode=...` 로 들고 다닌다. 남에게 검색 결과를 보낼 때 「검색창에 이걸
 * 치고 비슷 모드를 누르세요」 를 덧붙이지 않아도 된다.
 */

import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { MATCH_LABELS, destinationOf } from '@/modules/search/destinations'
import type { SearchHit } from '@/modules/search/destinations'
import { api } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { useResource } from '@/shared/hooks/useResource'

interface Group {
  kind: string
  label: string
  module: string
  hits: SearchHit[]
  truncated: boolean
}

interface Answer {
  query: string
  mode: string
  total: number
  groups: Group[]
}

const MODES = [
  { key: 'exact', label: '일치', hint: '정확히 그 이름' },
  { key: 'contains', label: '포함', hint: '그 말이 들어간 것' },
  { key: 'similar', label: '비슷', hint: '오타·표기 흔들림까지' },
] as const

export default function SearchPage() {
  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const mode = params.get('mode') ?? 'contains'
  const focus = params.get('kind')

  const [typed, setTyped] = useState(query)
  useEffect(() => setTyped(query), [query])

  // **타이핑마다 부르지 않는다.** 열세 종류를 훑는 질의라, 한 글자마다 보내면
  // 서버가 버려질 답을 계속 만든다.
  const [settled, setSettled] = useState(query)
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(typed.trim()), 250)
    return () => window.clearTimeout(timer)
  }, [typed])

  const { data, error, loading } = useResource<Answer | null>(
    () =>
      settled.length === 0
        ? Promise.resolve(null)
        : api.get<Answer>(
            `/search?q=${encodeURIComponent(settled)}&mode=${mode}` +
              (focus ? `&kind=${encodeURIComponent(focus)}` : '')
          ),
    [settled, mode, focus]
  )

  // 주소를 따라오게 한다 — 새로고침·공유가 같은 결과를 내야 한다.
  useEffect(() => {
    if (settled === query) return
    const next = new URLSearchParams(params)
    if (settled) next.set('q', settled)
    else next.delete('q')
    setParams(next, { replace: true })
  }, [settled])

  function choose(key: string, value: string | null) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next)
  }

  const groups = useMemo(() => data?.groups ?? [], [data])
  const active = MODES.find((one) => one.key === mode) ?? MODES[1]

  return (
    <div className="max-w-4xl">
      <PageHeader
        title="검색"
        description="재료·시료·시편·시험부터 장비·문헌 물성까지 한 번에 찾습니다."
      />

      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          placeholder="이름·번호 (예: SECC180 · DMA · 항복강도)"
          aria-label="검색어"
          className="max-w-md"
          autoFocus
        />
        <div className="flex gap-1">
          {MODES.map((one) => (
            <Button
              key={one.key}
              type="button"
              size="sm"
              variant={one.key === mode ? 'default' : 'outline'}
              onClick={() => choose('mode', one.key)}
            >
              {one.label}
            </Button>
          ))}
        </div>
        <span className="text-muted-foreground text-xs">{active.hint}</span>
      </div>

      {focus && (
        <div className="mt-3 flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">
            {groups[0]?.label ?? focus} 만 보는 중입니다.
          </span>
          <Button type="button" size="sm" variant="ghost" onClick={() => choose('kind', null)}>
            전체로 돌아가기
          </Button>
        </div>
      )}

      <ErrorNotice error={error} />

      <div className="mt-4 space-y-6">
        {settled.length === 0 && (
          <p className="text-muted-foreground text-sm">찾을 말을 입력하세요.</p>
        )}
        {settled.length > 0 && loading && !data && (
          <p className="text-muted-foreground text-sm">찾는 중…</p>
        )}
        {data && groups.length === 0 && (
          <p className="text-muted-foreground text-sm">
            「{settled}」 로 찾은 것이 없습니다.
            {mode !== 'similar' && ' 「비슷」 으로 바꾸면 오타·표기 차이까지 봅니다.'}
          </p>
        )}

        {groups.map((group) => (
          <section key={group.kind}>
            <div className="mb-1 flex items-baseline gap-2">
              <h2 className="text-sm font-semibold">{group.label}</h2>
              <span className="text-muted-foreground text-xs">
                {group.hits.length}건{group.truncated ? ' 이상' : ''}
              </span>
              {group.truncated && !focus && (
                <button
                  type="button"
                  className="text-primary text-xs underline"
                  onClick={() => choose('kind', group.kind)}
                >
                  이 종류만 더 보기
                </button>
              )}
            </div>
            <ul className="divide-y rounded-md border text-sm">
              {group.hits.map((hit) => {
                const where = destinationOf(hit)
                return (
                  <li
                    key={`${hit.kind}:${hit.id}`}
                    className="flex items-center justify-between gap-3 px-3 py-2"
                  >
                    <div className="min-w-0">
                      {where.href ? (
                        <Link to={where.href} className="font-medium hover:underline">
                          {hit.name}
                        </Link>
                      ) : (
                        <span className="font-medium">{hit.name}</span>
                      )}
                      <div className="text-muted-foreground text-xs">
                        {MATCH_LABELS[hit.matched] ?? hit.matched}
                        {where.approximate && ' · 목록에서 찾으세요'}
                      </div>
                    </div>
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </div>
    </div>
  )
}
