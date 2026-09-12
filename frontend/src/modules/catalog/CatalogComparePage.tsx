/**
 * 문헌 재료 비교 — **물성마다 대표값을 나란히.**
 *
 * 칸마다 tier 배지와 후보 수가 붙는다 — 그 숫자가 N개 중 하나라는 사실 자체가
 * 알아야 할 정보다(상세 화면과 같은 원칙). 줄의 최댓값 기준 상대 막대가
 * 크기 감을 준다. `?ids=` 라 링크로 공유된다.
 */

import { Plus, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import {
  CATEGORY_LABELS,
  DOMAIN_LABELS,
  TIER_LABELS,
  catalogApi,
  fmtConditions,
  fmtValueAs,
} from '@/modules/catalog/api'
import { UnitModeToggle, useUnitMode } from '@/modules/catalog/unitMode'
import type { CompareResult } from '@/modules/catalog/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { useResource } from '@/shared/hooks/useResource'

const MAX = 8

export default function CatalogComparePage() {
  const [params, setParams] = useSearchParams()
  const ids = (params.get('ids') ?? '').split(',').filter(Boolean)
  const [typed, setTyped] = useState('')
  const [found, setFound] = useState<{ id: string; name: string }[]>([])
  const [error, setError] = useState<Error | null>(null)
  const [units, setUnits] = useUnitMode()

  const result = useResource<CompareResult | null>(
    () => (ids.length >= 2 ? catalogApi.compare(ids) : Promise.resolve(null)),
    [params.get('ids')]
  )

  useEffect(() => {
    if (!typed.trim()) {
      setFound([])
      return
    }
    const timer = setTimeout(() => {
      catalogApi
        .materials({ q: typed.trim(), limit: 8 })
        .then((page) =>
          setFound(
            page.items
              .filter((one) => !ids.includes(String(one.id)))
              .map((one) => ({ id: String(one.id), name: one.name }))
          )
        )
        .catch((caught) =>
          setError(caught instanceof Error ? caught : new Error('검색하지 못했습니다.'))
        )
    }, 250)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- ids 는 문자열 파라미터로 본다
  }, [typed, params.get('ids')])

  function setIds(next: string[]) {
    setParams(next.length ? { ids: next.join(',') } : {}, { replace: true })
  }

  const materials = result.data?.materials ?? []
  const rows = result.data?.rows ?? []

  return (
    <div className="space-y-4">
      <PageHeader
        title="문헌 재료 비교"
        description={`문헌 재료를 최대 ${MAX}종까지 나란히 봅니다. 칸의 값은 상세 화면과 같은 대표값이고, 후보가 여럿이면 그 수가 함께 적힙니다.`}
      />
      <ErrorNotice error={error} />
      <ErrorNotice error={result.error} />

      <div className="flex flex-wrap items-center gap-2">
        {materials.map((one) => (
          <Badge key={one.id} variant="secondary" className="gap-1">
            {one.name}
            <button
              type="button"
              aria-label={`${one.name} 제거`}
              onClick={() => setIds(ids.filter((id) => id !== String(one.id)))}
            >
              <X className="size-3" />
            </button>
          </Badge>
        ))}
        <UnitModeToggle mode={units} onChange={setUnits} />
        {ids.length < MAX && (
          <div className="relative">
            <Input
              aria-label="비교할 재료 검색"
              placeholder="재료 이름으로 검색해 추가"
              className="w-72"
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
            />
            {found.length > 0 && (
              <div className="bg-background absolute z-10 mt-1 w-full rounded-md border shadow">
                {found.map((one) => (
                  <button
                    key={one.id}
                    type="button"
                    className="hover:bg-muted block w-full truncate px-3 py-1.5 text-left text-sm"
                    onClick={() => {
                      setIds([...ids, one.id])
                      setTyped('')
                      setFound([])
                    }}
                  >
                    <Plus className="mr-1 inline size-3" />
                    {one.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {ids.length < 2 && (
        <p className="text-muted-foreground rounded-md border py-10 text-center text-sm">
          재료를 두 종 이상 추가하면 표가 섭니다.
        </p>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className="bg-background sticky left-0 min-w-44 p-2 text-left">물성</th>
                {materials.map((one) => (
                  <th key={one.id} className="min-w-44 p-2 text-left">
                    <Link className="hover:underline" to={`/catalog/${one.id}`}>
                      {one.name}
                    </Link>
                    <div className="text-muted-foreground text-xs font-normal">
                      {CATEGORY_LABELS[one.category] ?? one.category}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const first = index === 0 || rows[index - 1].domain !== row.domain
                const numbers = row.cells
                  .map((cell) => cell.value_num)
                  .filter((value): value is number => value !== null && value !== undefined)
                const top = numbers.length > 0 ? Math.max(...numbers.map(Math.abs)) : 0
                return (
                  <tr key={row.property_key} className="border-b last:border-b-0">
                    <td className="bg-background sticky left-0 p-2">
                      {first && (
                        <div className="text-muted-foreground text-xs font-semibold">
                          {DOMAIN_LABELS[row.domain] ?? row.domain}
                        </div>
                      )}
                      {row.name}
                      {row.symbol && (
                        <span className="text-muted-foreground ml-1 text-xs">{row.symbol}</span>
                      )}
                    </td>
                    {row.cells.map((cell, at) => (
                      <td key={materials[at]?.id ?? at} className="p-2 align-top">
                        {cell.value_num === null && cell.value_text === null ? (
                          <span className="text-muted-foreground">—</span>
                        ) : (
                          <>
                            <div className="tabular-nums">
                              {cell.value_num !== null && cell.value_num !== undefined
                                ? fmtValueAs(units, cell.value_num, row.unit)
                                : cell.value_text}
                            </div>
                            {top > 0 &&
                              cell.value_num !== null &&
                              cell.value_num !== undefined &&
                              cell.value_num >= 0 && (
                                <div className="bg-muted mt-1 h-1 w-full rounded">
                                  <div
                                    className="bg-primary/60 h-1 rounded"
                                    style={{ width: `${(cell.value_num / top) * 100}%` }}
                                  />
                                </div>
                              )}
                            <div className="text-muted-foreground mt-0.5 text-xs">
                              {cell.quality_tier != null &&
                                (TIER_LABELS[cell.quality_tier] ?? `t${cell.quality_tier}`)}
                              {cell.n_candidates > 1 && ` · 후보 ${cell.n_candidates}`}
                              {cell.conditions && (
                                <span
                                  title={fmtConditions(
                                    cell.conditions as Record<string, unknown>
                                  )}
                                >
                                  {' · 조건'}
                                </span>
                              )}
                            </div>
                          </>
                        )}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {rows.length > 0 && (
        <Button variant="outline" size="sm" onClick={() => setIds([])}>
          모두 삭제
        </Button>
      )}
    </div>
  )
}
