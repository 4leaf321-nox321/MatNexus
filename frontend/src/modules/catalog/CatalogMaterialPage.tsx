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

import { FilePlus2, PackagePlus } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { AdoptDialog } from '@/modules/catalog/AdoptDialog'
import { ParameterSetsSection } from '@/modules/catalog/ParameterSetsSection'
import { CreateMaterialDialog } from '@/modules/catalog/CreateMaterialDialog'

import {
  CATEGORY_LABELS,
  DOMAIN_LABELS,
  TIER_LABELS,
  catalogApi,
  fmtDistinguishing,
  fmtRestConditions,
  fmtValueAs,
} from '@/modules/catalog/api'
import { UnitModeToggle, useUnitMode } from '@/modules/catalog/unitMode'
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

/** `bound: lower/upper` 를 사람 말로. 원본이 긴 설명을 적어 둔 경우도 있어 앞만 본다. */
function boundLabel(value: { distinguishing?: Record<string, unknown> | null }): string | null {
  const raw = value.distinguishing?.['bound']
  if (typeof raw !== 'string') return null
  const head = raw.toLowerCase()
  if (head.startsWith('lower') || head.startsWith('min')) return '범위 하한'
  if (head.startsWith('upper') || head.startsWith('max')) return '범위 상한'
  return null
}

export default function CatalogMaterialPage() {
  const { id = '' } = useParams()
  const stale = !UUID_PATTERN.test(id)
  const detail = useResource(
    () => (stale ? Promise.resolve(null) : catalogApi.material(id)),
    [id]
  )
  const item = detail.data
  const [adopting, setAdopting] = useState(false)
  const [creating, setCreating] = useState(false)
  const [units, setUnits] = useUnitMode()

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
          <Button size="sm" variant="outline" onClick={() => setCreating(true)}>
            <FilePlus2 className="size-4" />
            사내 재료로 등록
          </Button>
          <Badge variant="outline">{CATEGORY_LABELS[item.category] ?? item.category}</Badge>
          <Badge variant="outline">{item.subsystem ?? '미분류'}</Badge>
          {item.role && <Badge variant="secondary">{item.role}</Badge>}
          {item.manufacturer && (
            <span className="text-muted-foreground text-sm">{item.manufacturer}</span>
          )}
          {item.grade && <span className="text-muted-foreground text-sm">{item.grade}</span>}
          <span className="ml-auto">
            <UnitModeToggle mode={units} onChange={setUnits} />
          </span>
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
          {/* **폭을 열마다 못 박는다.** 안 박으면 값 열이 남는 폭을 다 먹고
              조건·등급·출처가 서로 겹친다 — 표가 자동으로 나누는 폭은 가장 긴
              한 줄을 따라가는데, 여기서 가장 긴 것이 대개 값이기 때문이다.
              값은 숫자와 단위라 넓을 이유가 없고, 조건이 길다. */}
          <div className="overflow-x-auto rounded-md border">
            <Table className="table-fixed">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[26%]">물성</TableHead>
                  <TableHead className="w-[16%]">값</TableHead>
                  <TableHead className="w-[34%]">조건</TableHead>
                  <TableHead className="w-[8%]">등급</TableHead>
                  <TableHead className="w-[16%]">출처</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {values.map((value) => (
                  <TableRow key={value.id} className={value.representative ? '' : 'opacity-80'}>
                    <TableCell className="align-top text-sm break-words">
                      {value.property_name}
                      {/* **한 이름에 변수가 여럿인 물성이 있다**(ADR 0029). Anand
                          하나에 9개 상수가 들어 있어서, 이름만 적으면 표에 같은
                          줄이 아홉 번 서고 무엇이 무엇인지 알 수 없다. */}
                      {value.term && (
                        <span className="ml-1 font-medium">· {value.term}</span>
                      )}
                      {value.symbol && !value.term && (
                        <span className="text-muted-foreground ml-1 text-xs">{value.symbol}</span>
                      )}
                      {value.n_candidates > 1 && value.representative && (
                        <Badge variant="secondary" className="ml-2">
                          대표값 · 후보 {value.n_candidates}
                        </Badge>
                      )}
                      {/* **범위의 한쪽이라는 것을 말한다.** 경쟁하는 두 측정이
                          아니라 한 범위의 양끝인데, 지금까지는 대표값 규칙이 둘 중
                          하나를 이기게 해 놓고 그 사실을 안 알렸다. */}
                      {boundLabel(value) && (
                        <Badge variant="outline" className="ml-2">
                          {boundLabel(value)}
                        </Badge>
                      )}
                      {!value.representative && (
                        <Badge variant="outline" className="text-muted-foreground ml-2">
                          대안 · {value.separated_by}
                        </Badge>
                      )}
                      {value.representative && (
                        <Link
                          to={`/metrology?key=${encodeURIComponent(value.property_key)}`}
                          className="text-muted-foreground hover:text-foreground ml-2 text-xs underline"
                          title="이 물성을 재는 기법과 장비"
                        >
                          측정법
                        </Link>
                      )}
                    </TableCell>
                    <TableCell className="align-top text-sm break-words tabular-nums">
                      {/* **변수마다 단위가 다르다.** 정의는 대개 `1`(무차원)이라고
                          적혀 있는데 실제로는 `MPa`·`1/s`·`K` 다. 그 값은 SI 로
                          저장돼 있지도 않아서 환산하지 않고 그대로 보여 준다 —
                          환산하면 150000 MPa 가 엉뚱한 수가 된다(ADR 0029 D2). */}
                      {value.value_num === null || value.value_num === undefined ? (
                        (value.value_text ?? '—')
                      ) : value.term_unit ? (
                        <>
                          {value.value_num}
                          <span className="text-muted-foreground ml-1 text-xs">
                            {value.term_unit === '1' ? '' : value.term_unit}
                          </span>
                        </>
                      ) : (
                        fmtValueAs(units, value.value_num, value.unit)
                      )}
                    </TableCell>
                    {/* **갈리는 조건이 먼저, 굵게.** 후보가 넷이면 사람이 넷을
                        눈으로 대조해서 무엇이 다른지 찾아야 했다 — 서버가 그 대조를
                        대신하고(`distinguishing`), 겹치는 조건은 뒤로 흐린다. */}
                    <TableCell className="align-top text-xs break-words">
                      {(() => {
                        const varying = fmtDistinguishing(
                          value.distinguishing as Record<string, unknown> | null
                        )
                        const rest = fmtRestConditions(
                          value.conditions as Record<string, unknown> | null,
                          value.distinguishing as Record<string, unknown> | null
                        )
                        if (varying.length === 0 && !rest) return <span className="text-muted-foreground">—</span>
                        return (
                          <>
                            {varying.length > 0 && (
                              <span className="text-foreground font-medium">
                                {varying.join(' · ')}
                              </span>
                            )}
                            {rest && (
                              <span className="text-muted-foreground">
                                {varying.length > 0 ? ' · ' : ''}
                                {rest}
                              </span>
                            )}
                          </>
                        )
                      })()}
                    </TableCell>
                    <TableCell className="align-top">
                      <TierBadge value={value} />
                    </TableCell>
                    <TableCell className="align-top break-words">
                      <SourceCell value={value} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </section>
      ))}

      {/* **묶음은 표 아래에 따로 선다.** 값 표에 낱개로 섞어 두면 같은 이름이
          아홉 번 서고, 무엇이 한 벌인지 안 보인다(ADR 0029). */}
      {id && <ParameterSetsSection materialId={id} />}

      {item && <AdoptDialog detail={item} open={adopting} onClose={() => setAdopting(false)} />}
      {item && (
        <CreateMaterialDialog detail={item} open={creating} onClose={() => setCreating(false)} />
      )}
    </div>
  )
}
