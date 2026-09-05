/**
 * 문헌 재료 상세 — **값·조건·등급·출처가 한 줄이고, 진 후보를 숨기지 않는다.**
 *
 * 같은 물성에 값이 여럿이면 서버가 대표를 골라 먼저 세우되(고체상→등급→기준온도
 * 근접), 밀린 후보도 **밀린 자리와 함께** 그대로 보여 준다 — 「선택기가 N개 중
 * 하나를 골랐다」 는 것 자체가 사용자가 알아야 할 정보다(MaterialTwin UX).
 *
 * tier4(추정·가정)도 똑같이 선다 — 배지로 구별만 한다. 추정값도 쓰라고 모은
 * 데이터다(2026-09-06 사용자 결정).
 */

import { PackagePlus } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { AdoptDialog } from '@/modules/catalog/AdoptDialog'

import {
  CATEGORY_LABELS,
  DOMAIN_LABELS,
  TIER_LABELS,
  catalogApi,
  fmtConditions,
  fmtValue,
} from '@/modules/catalog/api'
import type { CatalogValue } from '@/modules/catalog/api'
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

/** tier 배지 — 낮을수록 신뢰가 실린 표기. 4는 가정 표지가 있으면 「가정」. */
function TierBadge({ value }: { value: CatalogValue }) {
  const assumed = value.quality_tier === 4 && value.conditions?.['assumption'] === true
  const label = assumed ? '가정' : (TIER_LABELS[value.quality_tier] ?? `t${value.quality_tier}`)
  if (value.quality_tier === 1) return <Badge>{label}</Badge>
  if (value.quality_tier === 2) return <Badge variant="secondary">{label}</Badge>
  if (value.quality_tier === 3) return <Badge variant="outline">{label}</Badge>
  return (
    <Badge variant="outline" className="border-amber-500 text-amber-700 dark:text-amber-500">
      {label}
    </Badge>
  )
}

function SourceCell({ value }: { value: CatalogValue }) {
  const source = value.source
  if (!source) return <span className="text-muted-foreground">—</span>
  const href = source.doi ? `https://doi.org/${source.doi}` : (source.url ?? undefined)
  const label = source.title ?? source.publisher ?? source.kind
  return (
    <div className="max-w-72 text-xs">
      {href ? (
        <a className="hover:underline" href={href} target="_blank" rel="noreferrer">
          {label}
        </a>
      ) : (
        <span>{label}</span>
      )}
      <span className="text-muted-foreground">
        {source.year ? ` · ${source.year}` : ''}
        {value.source_detail ? ` · ${value.source_detail}` : ''}
      </span>
    </div>
  )
}

//: 재료 상세는 UUID 만 받는다. UUID 가 아닌 주소가 여기 닿는 것은 **옛 번들**이
//: /catalog/compare 같은 새 경로를 :id 로 잘못 잡은 것이다(2026-09-06 실측 두 번).
//: API 를 불러 422 를 보여 주면 사람은 데이터 문제로 읽는다 — 여기서 말한다.
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export default function CatalogMaterialPage() {
  const { id = '' } = useParams()
  const stale = !UUID_PATTERN.test(id)
  const detail = useResource(
    () => (stale ? Promise.resolve(null) : catalogApi.material(id)),
    [id]
  )
  const item = detail.data
  const [adopting, setAdopting] = useState(false)

  if (stale) {
    return (
      <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
        이 화면 주소(/catalog/{id})는 새 버전에 있는 화면입니다 — 브라우저를
        새로고침(Ctrl+F5)한 뒤 다시 눌러 주세요.
      </div>
    )
  }

  const byDomain = new Map<string, CatalogValue[]>()
  for (const value of item?.values ?? []) {
    const list = byDomain.get(value.domain) ?? []
    list.push(value)
    byDomain.set(value.domain, list)
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={item?.name ?? '문헌 재료'}
        description="문헌·데이터시트에서 온 값입니다. 같은 물성의 후보가 여럿이면 대표가 먼저 서고, 진 후보는 밀린 이유와 함께 보입니다."
      />

      <ErrorNotice error={detail.error} />

      {item && (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => setAdopting(true)} disabled={item.values.length === 0}>
            <PackagePlus className="size-4" />
            사내 재료에 채우기
          </Button>
          <Badge variant="outline">{CATEGORY_LABELS[item.category] ?? item.category}</Badge>
          <Badge variant="outline">{item.subsystem ?? '미분류'}</Badge>
          {item.role && <Badge variant="secondary">{item.role}</Badge>}
          {item.manufacturer && (
            <span className="text-muted-foreground text-sm">{item.manufacturer}</span>
          )}
          {item.grade && <span className="text-muted-foreground text-sm">{item.grade}</span>}
        </div>
      )}
      {item?.description && <p className="text-muted-foreground text-sm">{item.description}</p>}

      {item && item.values.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          이 재료에 등록된 물성값이 없습니다.
        </div>
      )}

      {[...byDomain.entries()].map(([domain, values]) => (
        <section key={domain} className="space-y-2">
          <h2 className="text-sm font-semibold">
            {DOMAIN_LABELS[domain] ?? domain}
            <span className="text-muted-foreground ml-2 text-xs font-normal">
              {values.length}건
            </span>
          </h2>
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>물성</TableHead>
                  <TableHead>값</TableHead>
                  <TableHead>조건</TableHead>
                  <TableHead>등급</TableHead>
                  <TableHead>출처</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {values.map((value) => (
                  <TableRow key={value.id} className={value.representative ? '' : 'opacity-80'}>
                    <TableCell className="text-sm">
                      {value.property_name}
                      {value.symbol && (
                        <span className="text-muted-foreground ml-1 text-xs">{value.symbol}</span>
                      )}
                      {value.n_candidates > 1 && value.representative && (
                        <Badge variant="secondary" className="ml-2">
                          대표값 · 후보 {value.n_candidates}
                        </Badge>
                      )}
                      {!value.representative && (
                        <Badge variant="outline" className="text-muted-foreground ml-2">
                          대안 · {value.separated_by}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-sm tabular-nums">
                      {value.value_num !== null && value.value_num !== undefined
                        ? fmtValue(value.value_num, value.unit)
                        : (value.value_text ?? '—')}
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-64 text-xs">
                      {fmtConditions(value.conditions as Record<string, unknown> | null) || '—'}
                    </TableCell>
                    <TableCell>
                      <TierBadge value={value} />
                    </TableCell>
                    <TableCell>
                      <SourceCell value={value} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </section>
      ))}

      {item && <AdoptDialog detail={item} open={adopting} onClose={() => setAdopting(false)} />}
    </div>
  )
}
