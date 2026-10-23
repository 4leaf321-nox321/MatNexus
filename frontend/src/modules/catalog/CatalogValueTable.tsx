/**
 * 문헌 값 **전부**를 한 줄씩 — 재료 상세의 「전체 값」 탭(2026-10-22 에 탭으로 옮겼다).
 *
 * 같은 물성에 값이 여럿이면 서버가 대표를 골라 먼저 세우되, 밀린 후보도 **밀린 자리와 함께**
 * 그대로 보인다 — 「선택기가 N개 중 하나를 골랐다」 는 것 자체가 사용자가 알아야 할 정보다.
 * tier4(추정·가정)도 똑같이 선다 — 배지로 구별만 한다(2026-09-06 사용자 결정).
 *
 * 거르개(찾기 · 등급 · 방법)는 **보는 것만** 줄인다 — 대표 표시는 거르기 전 전체에서 정한 그대로다.
 */

import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import {
  DOMAIN_LABELS,
  TIER_LABELS,
  fmtDistinguishing,
  fmtRestConditions,
  fmtValueAs,
} from '@/modules/catalog/api'
import type { CatalogValue, UnitMode } from '@/modules/catalog/api'
import { METHOD_LABELS, isAssumed } from '@/modules/catalog/catalogForms'
import { Badge } from '@/shared/components/ui/badge'
import { Input } from '@/shared/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'

/**
 * 값 표의 칸 — **접는다.** 표 칸의 기본값은 `whitespace-nowrap` 인데, 이 표는 열 폭을 박아
 * 두어(`table-fixed`) 안 접힌 글이 옆 칸 위로 넘친다. 띄어 쓰지 않은 긴 토막(DOI · 식 · 단위)도
 * 칸 안에서 끊는다.
 */
const CELL = 'align-top whitespace-normal wrap-anywhere'

/** tier 배지 — 낮을수록 신뢰가 실린 표기. 4는 가정 표지가 있으면 「가정」. */
export function TierBadge({
  tier,
  assumed = false,
}: {
  tier: number
  assumed?: boolean
}) {
  const label = assumed && tier === 4 ? '가정' : (TIER_LABELS[tier] ?? `t${tier}`)
  if (tier === 1) return <Badge>{label}</Badge>
  if (tier === 2) return <Badge variant="secondary">{label}</Badge>
  if (tier === 3) return <Badge variant="outline">{label}</Badge>
  return (
    <Badge variant="outline" className="border-amber-500 text-amber-700 dark:text-amber-500">
      {label}
    </Badge>
  )
}

type Source = NonNullable<CatalogValue['source']>

/** 출처 한 토막 — DOI 가 있으면 DOI 로, 없으면 URL 로 건다. */
export function SourceLabel({ source, detail }: { source: Source | null; detail?: string | null }) {
  if (!source) return <span className="text-muted-foreground">—</span>
  const href = source.doi ? `https://doi.org/${source.doi}` : (source.url ?? undefined)
  const label = source.title ?? source.publisher ?? source.kind
  return (
    <div className="text-xs">
      {href ? (
        <a className="hover:underline" href={href} target="_blank" rel="noreferrer">
          {label}
        </a>
      ) : (
        <span>{label}</span>
      )}
      <span className="text-muted-foreground">
        {source.year ? ` · ${source.year}` : ''}
        {detail ? ` · ${detail}` : ''}
      </span>
    </div>
  )
}

/**
 * **원본에서 빠진 것**(2026-10-04) — 원본(MaterialTwin) 스냅샷이 이 줄을 지웠다. 이관은 지우지
 * 않고 표시만 한다(선언 물성 · 카드가 근거로 쥐고 있을 수 있다). 대표값 · 값 검색 · 덱에는 쓰이지
 * 않는다.
 */
export function MissingBadge({ at, what }: { at: string; what: string }) {
  const when = new Date(at).toLocaleDateString('ko-KR')
  return (
    <Badge
      variant="outline"
      className="border-amber-500/60 text-amber-700 dark:text-amber-400"
      title={`원본(MaterialTwin) 스냅샷에서 ${when} 에 빠진 ${what}입니다. 지우지 않고 남겨 두었고, 대표값 · 값 검색 · 덱에는 쓰지 않습니다.`}
    >
      원본에서 빠짐
    </Badge>
  )
}

/** `bound: lower/upper` 를 사람 말로. 원본이 긴 설명을 적어 둔 경우도 있어 앞만 본다. */
function boundLabel(value: { distinguishing?: Record<string, unknown> | null }): string | null {
  const raw = value.distinguishing?.['bound']
  if (typeof raw !== 'string') return null
  const head = raw.toLowerCase()
  if (head.startsWith('lower') || head.startsWith('min')) return '범위 하한'
  if (head.startsWith('upper') || head.startsWith('max')) return '범위 상한'
  return null
}

/** 값 한 칸 — 계수 묶음의 항은 그 항의 단위 그대로(ADR 0029 D2), 나머지는 단위 모드대로. */
export function ValueText({ value, units }: { value: CatalogValue; units: UnitMode }) {
  if (value.value_num === null || value.value_num === undefined) return <>{value.value_text ?? '—'}</>
  if (value.term_unit) {
    return (
      <>
        {value.value_num}
        <span className="text-muted-foreground ml-1 text-xs">
          {value.term_unit === '1' ? '' : value.term_unit}
        </span>
      </>
    )
  }
  return <>{fmtValueAs(units, value.value_num, value.unit)}</>
}

/** 조건 한 칸 — **갈리는 조건이 먼저, 굵게**, 겹치는 조건은 뒤로 흐리게. */
export function ConditionText({ value }: { value: CatalogValue }) {
  const varying = fmtDistinguishing(value.distinguishing as Record<string, unknown> | null)
  const rest = fmtRestConditions(
    value.conditions as Record<string, unknown> | null,
    value.distinguishing as Record<string, unknown> | null
  )
  if (varying.length === 0 && !rest) return <span className="text-muted-foreground">—</span>
  return (
    <>
      {varying.length > 0 && <span className="text-foreground font-medium">{varying.join(' · ')}</span>}
      {rest && (
        <span className="text-muted-foreground">
          {varying.length > 0 ? ' · ' : ''}
          {rest}
        </span>
      )}
    </>
  )
}

/** 값 표의 줄 — 「전체 값」 탭과 「물성 요약」 의 펼친 후보가 같은 줄을 쓴다. */
export function ValueRows({
  values,
  units,
  canRemove,
  onRemove,
}: {
  values: CatalogValue[]
  units: UnitMode
  canRemove: (value: CatalogValue) => boolean
  onRemove: (value: CatalogValue) => void
}) {
  return (
    <>
      {values.map((value) => (
        <TableRow key={value.id} className={value.representative ? '' : 'opacity-80'}>
          <TableCell className={CELL}>
            {/* 이름 뒤 배지는 **한 덩이로 줄을 바꾼다** — 글 사이에 섞어 흘리면 배지가 줄 끝에서
                잘리거나 옆 칸으로 넘친다. */}
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span>
                {value.property_name}
                {/* **한 이름에 변수가 여럿인 물성이 있다**(ADR 0029). Anand 하나에 9개 상수가
                    들어 있어서, 이름만 적으면 같은 줄이 아홉 번 서고 무엇이 무엇인지 모른다. */}
                {value.term && <span className="ml-1 font-medium">· {value.term}</span>}
                {value.symbol && !value.term && (
                  <span className="text-muted-foreground ml-1 text-xs">{value.symbol}</span>
                )}
              </span>
              {value.n_candidates > 1 && value.representative && (
                <Badge variant="secondary">대표값 · 후보 {value.n_candidates}</Badge>
              )}
              {/* **범위의 한쪽이라는 것을 말한다.** 경쟁하는 두 측정이 아니라 한 범위의 양끝이다. */}
              {boundLabel(value) && <Badge variant="outline">{boundLabel(value)}</Badge>}
              {/* 원본에서 빠진 값은 「대안」 이 아니다 — 대표 후보에서 아예 빠졌다. */}
              {value.source_missing_at ? (
                <MissingBadge at={value.source_missing_at} what="값" />
              ) : (
                !value.representative && (
                  <Badge variant="outline" className="text-muted-foreground">
                    대안 · {value.separated_by}
                  </Badge>
                )
              )}
              {value.series_id && (
                <Badge variant="outline" title="직접 넣은 곡선 · 계수 묶음 한 벌의 점입니다">
                  묶음의 점
                </Badge>
              )}
              {value.origin === 'local' && (
                <Badge variant="outline" title="MatNexus 에서 직접 넣은 값">
                  직접 넣음{value.created_by ? ` · ${value.created_by}` : ''}
                </Badge>
              )}
              {canRemove(value) && (
                <button
                  type="button"
                  aria-label={`${value.property_name} 값 삭제`}
                  className="text-muted-foreground hover:text-destructive rounded p-0.5"
                  onClick={() => onRemove(value)}
                >
                  <Trash2 className="size-3.5" />
                </button>
              )}
              {value.representative && (
                <Link
                  to={`/metrology?key=${encodeURIComponent(value.property_key)}`}
                  className="text-muted-foreground hover:text-foreground text-xs underline"
                  title="이 물성을 재는 기법과 장비"
                >
                  측정법
                </Link>
              )}
            </div>
          </TableCell>
          <TableCell className={`${CELL} tabular-nums`}>
            <ValueText value={value} units={units} />
          </TableCell>
          <TableCell className={CELL}>
            <TierBadge tier={value.quality_tier} assumed={isAssumed(value)} />
          </TableCell>
          <TableCell className={CELL}>
            <ConditionText value={value} />
          </TableCell>
          <TableCell className={CELL}>
            <SourceLabel source={value.source ?? null} detail={value.source_detail} />
          </TableCell>
        </TableRow>
      ))}
    </>
  )
}

/**
 * **폭을 열마다 못 박는다.** 안 박으면 값 열이 남는 폭을 다 먹고 조건·등급·출처가 서로
 * 겹친다. 폭을 박았으면 접기도 켠다(`CELL`, 2026-10-04 지적). 등급은 배지 하나라 고정 폭이다.
 */
export function ValueTableFrame({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-md border">
      <Table className="min-w-[50rem] table-fixed">
        <TableHeader>
          <TableRow>
            <TableHead className="w-[24%]">물성</TableHead>
            <TableHead className="w-[14%]">값</TableHead>
            <TableHead className="w-20">등급</TableHead>
            <TableHead>조건</TableHead>
            <TableHead className="w-[22%]">출처</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>{children}</TableBody>
      </Table>
    </div>
  )
}

export function CatalogValueTable({
  values,
  units,
  canRemove,
  onRemove,
}: {
  values: CatalogValue[]
  units: UnitMode
  canRemove: (value: CatalogValue) => boolean
  onRemove: (value: CatalogValue) => void
}) {
  const [query, setQuery] = useState('')
  const [tier, setTier] = useState('')
  const [method, setMethod] = useState('')
  const needle = query.trim().toLowerCase()
  const shown = values.filter(
    (value) =>
      (!needle ||
        value.property_name.toLowerCase().includes(needle) ||
        value.property_key.toLowerCase().includes(needle) ||
        (value.term ?? '').toLowerCase().includes(needle)) &&
      (!tier || String(value.quality_tier) === tier) &&
      (!method || value.method === method)
  )
  const methods = [...new Set(values.map((value) => value.method ?? '').filter(Boolean))].sort()

  const byDomain = new Map<string, CatalogValue[]>()
  for (const value of shown) {
    const list = byDomain.get(value.domain) ?? []
    list.push(value)
    byDomain.set(value.domain, list)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          aria-label="물성 찾기"
          className="h-8 w-56"
          placeholder="물성 이름 · 키 · 항"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <select
          aria-label="등급"
          className="border-input bg-background h-8 rounded-md border px-2 text-sm"
          value={tier}
          onChange={(event) => setTier(event.target.value)}
        >
          <option value="">등급 전체</option>
          {[1, 2, 3, 4].map((one) => (
            <option key={one} value={String(one)}>
              {TIER_LABELS[one] ?? one}
            </option>
          ))}
        </select>
        <select
          aria-label="방법"
          className="border-input bg-background h-8 rounded-md border px-2 text-sm"
          value={method}
          onChange={(event) => setMethod(event.target.value)}
        >
          <option value="">방법 전체</option>
          {methods.map((one) => (
            <option key={one} value={one}>
              {METHOD_LABELS[one] ?? one}
            </option>
          ))}
        </select>
        <span className="text-muted-foreground text-xs">
          {shown.length === values.length ? `${values.length}건` : `${values.length}건 중 ${shown.length}건`}
        </span>
      </div>

      {shown.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-8 text-center text-sm">
          고른 조건에 맞는 값이 없습니다.
        </div>
      )}

      {[...byDomain.entries()].map(([domain, list]) => (
        <section key={domain} className="space-y-2">
          <h2 className="text-sm font-semibold">
            {DOMAIN_LABELS[domain] ?? domain}
            <span className="text-muted-foreground ml-2 text-xs font-normal">{list.length}건</span>
          </h2>
          <ValueTableFrame>
            <ValueRows values={list} units={units} canRemove={canRemove} onRemove={onRemove} />
          </ValueTableFrame>
        </section>
      ))}
    </div>
  )
}
