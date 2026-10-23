/**
 * 「물성 요약」 탭 — **물성 하나에 한 줄**(2026-10-22, ADR 0067).
 *
 * 값이 366건인 재료도 물성이 아홉이면 아홉 줄이다. 줄마다 대표값 · 등급 · 값 수 · 갈리는 조건의
 * 범위(「온도 25 °C ~ 150 °C」)를 보이고, 펼치면 그 물성의 후보 전부와 선이 선다. 선이 있으면
 * 「곡선 n」 이 「곡선 · 표」 탭으로, 계수 묶음의 항만 있는 물성은 「계수 묶음」 탭으로 보낸다 —
 * 같은 이름이 아홉 번 서던 자리다(ADR 0029).
 */

import { ChevronDown, ChevronRight, LineChart } from 'lucide-react'
import { Fragment, useState } from 'react'

import { DOMAIN_LABELS } from '@/modules/catalog/api'
import type { CatalogValue, UnitMode } from '@/modules/catalog/api'
import { axisName, axisUnit } from '@/modules/catalog/catalogShape'
import type { AxisRange, PropertyGroup } from '@/modules/catalog/catalogShape'
import { TierBadge, ValueRows, ValueTableFrame, ValueText } from '@/modules/catalog/CatalogValueTable'
import { isAssumed } from '@/modules/catalog/catalogForms'
import { Badge } from '@/shared/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { formatScalar } from '@/shared/units'

export type CatalogTab = 'summary' | 'curves' | 'sets' | 'sources' | 'values'

/** 범위 하나를 사람 말로 — 단위는 표(`shared/units`)가 정한다(K → °C). */
function rangeText(range: AxisRange): string {
  const unit = axisUnit(range.key)
  const at = (value: number) => (unit ? formatScalar(value, unit) : String(value))
  return `${axisName(range.key)} ${at(range.min)} ~ ${at(range.max)}`
}

export function PropertySummary({
  groups,
  units,
  canRemove,
  onRemove,
  onOpenTab,
}: {
  groups: PropertyGroup[]
  units: UnitMode
  canRemove: (value: CatalogValue) => boolean
  onRemove: (value: CatalogValue) => void
  onOpenTab: (tab: CatalogTab) => void
}) {
  const [open, setOpen] = useState<Set<string>>(new Set())
  const byDomain = new Map<string, PropertyGroup[]>()
  for (const group of groups) {
    const list = byDomain.get(group.domain) ?? []
    list.push(group)
    byDomain.set(group.domain, list)
  }

  function toggle(key: string) {
    setOpen((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return (
    <div className="space-y-4">
      {[...byDomain.entries()].map(([domain, list]) => (
        <section key={domain} className="space-y-2">
          <h2 className="text-sm font-semibold">
            {DOMAIN_LABELS[domain] ?? domain}
            <span className="text-muted-foreground ml-2 text-xs font-normal">물성 {list.length}</span>
          </h2>
          <div className="overflow-x-auto rounded-md border">
            <Table className="min-w-[46rem]">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[30%]">물성</TableHead>
                  <TableHead>대표값</TableHead>
                  <TableHead>등급</TableHead>
                  <TableHead className="text-right">값</TableHead>
                  <TableHead>조건 범위</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((group) => {
                  const expanded = open.has(group.propertyKey)
                  return (
                    <Fragment key={group.propertyKey}>
                      <TableRow>
                        <TableCell>
                          <button
                            type="button"
                            className="flex items-center gap-1 text-left hover:underline"
                            aria-expanded={expanded}
                            aria-label={`${group.name} 펼치기`}
                            onClick={() => toggle(group.propertyKey)}
                          >
                            {expanded ? (
                              <ChevronDown className="size-3.5 shrink-0" />
                            ) : (
                              <ChevronRight className="size-3.5 shrink-0" />
                            )}
                            <span>{group.name}</span>
                            {group.symbol && (
                              <span className="text-muted-foreground ml-1">{group.symbol}</span>
                            )}
                          </button>
                        </TableCell>
                        <TableCell className="tabular-nums">
                          {group.parameterized ? (
                            <button
                              type="button"
                              className="text-primary hover:underline"
                              onClick={() => onOpenTab('sets')}
                            >
                              계수 묶음 · 항 {group.values.length}
                            </button>
                          ) : (
                            <ValueText value={group.head} units={units} />
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-1">
                            {group.tiers.map((tier) => (
                              <TierBadge
                                key={tier}
                                tier={tier}
                                assumed={group.values.some(
                                  (one) => one.quality_tier === tier && isAssumed(one)
                                )}
                              />
                            ))}
                          </div>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{group.values.length}</TableCell>
                        <TableCell>
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                            {group.ranges.length === 0 ? (
                              <span className="text-muted-foreground">—</span>
                            ) : (
                              group.ranges.slice(0, 3).map((range) => (
                                <span key={range.key}>{rangeText(range)}</span>
                              ))
                            )}
                            {group.curves > 0 && (
                              <button
                                type="button"
                                className="text-primary flex items-center gap-1 hover:underline"
                                onClick={() => onOpenTab('curves')}
                              >
                                <LineChart className="size-3.5" />
                                곡선 {group.curves}
                              </button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                      {expanded && (
                        <TableRow>
                          <TableCell colSpan={5} className="bg-muted/30">
                            <ValueTableFrame>
                              <ValueRows
                                values={group.values}
                                units={units}
                                canRemove={canRemove}
                                onRemove={onRemove}
                              />
                            </ValueTableFrame>
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </section>
      ))}
      {groups.length > 0 && (
        <p className="text-muted-foreground text-xs">
          <Badge variant="outline" className="mr-1">
            팁
          </Badge>
          물성 이름을 누르면 후보 전부가 펼쳐집니다. 값 하나하나를 거르며 보려면 「전체 값」 탭.
        </p>
      )}
    </div>
  )
}
