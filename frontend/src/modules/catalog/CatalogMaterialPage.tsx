/**
 * 문헌 재료 상세 — **요약 + 탭**(2026-10-22, ADR 0067 · 사용자 결정).
 *
 *   물성 요약   물성 하나에 한 줄 — 대표값 · 등급 · 값 수 · 조건 범위. 펼치면 후보 전부
 *   곡선 · 표   직접 넣은 한 벌(저장된 묶음)과 화면이 조건축을 따라 이은 선 — 둘을 다른 이름으로
 *   계수 묶음   Anand · Prony 같은 식의 계수 한 벌(ADR 0029)
 *   출처        출처 하나에 한 줄 — 값 수 · 물성 수 · 등급
 *   전체 값     값 하나가 한 줄 — 진 후보를 숨기지 않는다(대표 먼저, 밀린 자리와 함께) + 거르개
 *
 * 전에는 「전체 값」 하나뿐이라 값이 366건인 재료(SAC-Q)는 같은 물성 이름이 수십 줄 섰고, 그것이
 * 온도를 따라 이어진 한 곡선이라는 것은 조건 칸을 눈으로 대조해야 알았다. 탭은 주소(`?tab=`)에
 * 남는다 — 링크로 건넨 사람이 같은 탭을 본다.
 *
 * tier4(추정·가정)도 똑같이 선다 — 배지로 구별만 한다(2026-09-06 사용자 결정). **직접 넣은 값**
 * (MCP·API·화면, 2026-09-12)은 「직접 넣음 · 누구」 로 구별되고, 넣은 사람과 관리자만 지운다.
 */

import { FilePlus2, LineChart, PackagePlus, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import { AddValueDialog } from '@/modules/catalog/AddValueDialog'
import { AdoptDialog } from '@/modules/catalog/AdoptDialog'
import { CatalogValueTable, MissingBadge, TierBadge } from '@/modules/catalog/CatalogValueTable'
import { CreateMaterialDialog } from '@/modules/catalog/CreateMaterialDialog'
import { CurvesPanel, SeriesCard } from '@/modules/catalog/CurvesPanel'
import { ParameterSetsSection } from '@/modules/catalog/ParameterSetsSection'
import { PropertySummary } from '@/modules/catalog/PropertySummary'
import type { CatalogTab } from '@/modules/catalog/PropertySummary'
import { SeriesDialog } from '@/modules/catalog/SeriesDialog'
import { SourcesTable } from '@/modules/catalog/SourcesTable'
import { SyntheticCurveSection } from '@/modules/catalog/SyntheticCurveSection'
import { CATEGORY_LABELS, catalogApi } from '@/modules/catalog/api'
import type { CatalogSeries, CatalogValue } from '@/modules/catalog/api'
import {
  autoCurves,
  propertyGroups,
  seriesCurves,
  sourceRows,
  tierCounts,
} from '@/modules/catalog/catalogShape'
import { UnitModeToggle, useUnitMode } from '@/modules/catalog/unitMode'
import { useAuth } from '@/shared/auth/AuthContext'
import { isSystemAdmin } from '@/shared/auth/roles'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { useResource } from '@/shared/hooks/useResource'

/** 합성 곡선의 강도 입력 — 서버 `declared_card.SYNTH_KEYS` 의 앞 둘. */
const SYNTH_STRENGTHS = new Set(['mechanical.yield_strength', 'mechanical.tensile_strength'])

const TABS: CatalogTab[] = ['summary', 'curves', 'sets', 'sources', 'values']

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
  const [creating, setCreating] = useState(false)
  const [adding, setAdding] = useState(false)
  const [addingSeries, setAddingSeries] = useState(false)
  const [added, setAdded] = useState<string | null>(null)
  const [units, setUnits] = useUnitMode()
  const { user } = useAuth()
  const [removeError, setRemoveError] = useState<Error | null>(null)
  const [params, setParams] = useSearchParams()
  const asked = params.get('tab') as CatalogTab | null
  const tab: CatalogTab = asked && TABS.includes(asked) ? asked : 'summary'

  function openTab(next: CatalogTab) {
    setParams(
      (current) => {
        const copy = new URLSearchParams(current)
        copy.set('tab', next)
        return copy
      },
      { replace: true }
    )
  }

  const values = useMemo(() => item?.values ?? [], [item])
  const series = useMemo(() => item?.series ?? [], [item])
  const seriesLines = useMemo(() => seriesCurves(series, values), [series, values])
  const autoLines = useMemo(() => autoCurves(values), [values])
  const groups = useMemo(
    () => propertyGroups(values, [...seriesLines, ...autoLines]),
    [values, seriesLines, autoLines]
  )
  const tiers = tierCounts(values)
  const sourceCount = sourceRows(values).length

  /** 직접 넣은 낱값을 넣은 사람이거나 관리자면 지울 수 있다 — 서버가 다시 확인한다. 한 벌의 점은
   *  낱개로 안 지운다(벌째 지운다). */
  function canRemove(value: CatalogValue): boolean {
    if (value.origin !== 'local' || value.series_id) return false
    return isSystemAdmin(user) || (value.created_by != null && value.created_by === user?.display_name)
  }

  function canRemoveSeries(one: CatalogSeries): boolean {
    return isSystemAdmin(user) || (one.created_by != null && one.created_by === user?.display_name)
  }

  async function remove(value: CatalogValue) {
    if (!window.confirm(`'${value.property_name}' 값을 지울까요? 되돌릴 수 없습니다.`)) return
    setRemoveError(null)
    try {
      await catalogApi.deleteValue(value.id)
      detail.reload()
    } catch (caught) {
      setRemoveError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
    }
  }

  async function removeSeries(one: CatalogSeries) {
    if (!window.confirm(`'${one.label}' 한 벌(점 ${one.point_count}개)을 지울까요? 되돌릴 수 없습니다.`)) {
      return
    }
    setRemoveError(null)
    try {
      await catalogApi.deleteSeries(one.id)
      detail.reload()
    } catch (caught) {
      setRemoveError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
    }
  }

  if (stale) {
    return (
      <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
        이 화면 주소(/catalog/{id})는 새 버전에 있는 화면입니다 — 브라우저를
        새로고침(Ctrl+F5)한 뒤 다시 눌러 주세요.
      </div>
    )
  }

  const curveSets = series.filter((one) => one.kind === 'curve').length
  const parameterSets = series.filter((one) => one.kind === 'parameter_set')

  return (
    <div className="space-y-4">
      <PageHeader
        title={item?.name ?? '문헌 재료'}
        description="문헌·데이터시트에서 온 값입니다. 같은 물성의 후보가 여럿이면 대표가 먼저 서고, 진 후보는 밀린 이유와 함께 보입니다."
      />

      <ErrorNotice error={detail.error} />
      <ErrorNotice error={removeError} />

      {item && (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => setAdopting(true)} disabled={item.values.length === 0}>
            <PackagePlus className="size-4" />
            사내 재료에 반영
          </Button>
          <Button size="sm" variant="outline" onClick={() => setCreating(true)}>
            <FilePlus2 className="size-4" />
            사내 재료로 등록
          </Button>
          <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
            <Plus className="size-4" />
            값 입력
          </Button>
          <Button size="sm" variant="outline" onClick={() => setAddingSeries(true)}>
            <LineChart className="size-4" />
            곡선 입력
          </Button>
          <Badge variant="outline">{CATEGORY_LABELS[item.category] ?? item.category}</Badge>
          <Badge variant="outline">{item.subsystem ?? '미분류'}</Badge>
          {item.source_missing_at && <MissingBadge at={item.source_missing_at} what="재료" />}
          {item.origin === 'local' && (
            <Badge variant="outline" title="MatNexus 에서 직접 넣은 재료">
              직접 넣음{item.created_by ? ` · ${item.created_by}` : ''}
            </Badge>
          )}
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

      {/* **한눈에 무엇이 얼마나 있나** — 값 · 물성 · 곡선 · 출처 수와 등급 분포. */}
      {item && item.values.length > 0 && (
        <div aria-label="문헌 재료 요약" className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <span>
            값 <b className="tabular-nums">{values.length}</b>
          </span>
          <span>
            물성 <b className="tabular-nums">{groups.length}</b>
          </span>
          <span>
            곡선 <b className="tabular-nums">{seriesLines.length + autoLines.length}</b>
            <span className="text-muted-foreground">
              {' '}
              (입력 {curveSets}벌 · 자동 {autoLines.length})
            </span>
          </span>
          <span>
            출처 <b className="tabular-nums">{sourceCount}</b>
          </span>
          <span className="flex items-center gap-1">
            {[...tiers.entries()].map(([tier, count]) => (
              <span key={tier} className="flex items-center gap-0.5">
                <TierBadge tier={tier} />
                <span className="tabular-nums">{count}</span>
              </span>
            ))}
          </span>
        </div>
      )}
      {added && (
        <p className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm dark:border-emerald-800 dark:bg-emerald-950">
          {added}
        </p>
      )}

      {item && item.values.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          이 재료에 등록된 물성값이 없습니다.
        </div>
      )}

      {item && item.values.length > 0 && (
        <Tabs value={tab} onValueChange={(next) => openTab(next as CatalogTab)}>
          <TabsList>
            <TabsTrigger value="summary">물성 요약 {groups.length}</TabsTrigger>
            <TabsTrigger value="curves">곡선 · 표 {seriesLines.length + autoLines.length}</TabsTrigger>
            <TabsTrigger value="sets">계수 묶음</TabsTrigger>
            <TabsTrigger value="sources">출처 {sourceCount}</TabsTrigger>
            <TabsTrigger value="values">전체 값 {values.length}</TabsTrigger>
          </TabsList>
          <TabsContent value="summary" className="mt-3">
            <PropertySummary
              groups={groups}
              units={units}
              canRemove={canRemove}
              onRemove={(value) => void remove(value)}
              onOpenTab={openTab}
            />
          </TabsContent>
          <TabsContent value="curves" className="mt-3 space-y-6">
            <CurvesPanel
              series={series}
              values={values}
              seriesLines={seriesLines}
              autoLines={autoLines}
              canRemove={canRemoveSeries}
              onRemove={(one) => void removeSeries(one)}
            />
            {/* 항복이나 인장강도가 있어야 곡선을 지을 수 있다 — 없으면 단추를 세우지 않는다
                (누르고 「모자랍니다」 만 보게 하지 않는다). 정확한 판정은 서버가 한다. */}
            {values.some((value) => SYNTH_STRENGTHS.has(value.property_key)) && (
              <SyntheticCurveSection materialId={id} />
            )}
          </TabsContent>
          <TabsContent value="sets" className="mt-3 space-y-3">
            {/* **직접 넣은 계수 묶음**은 머리째 보이고 지울 수 있다. 아래 목록은 이관해 온 것까지
                값의 `set_id` 로 묶은 것이라 같은 벌이 거기에도 선다. */}
            {parameterSets.map((one) => (
              <SeriesCard
                key={one.id}
                series={one}
                values={values}
                lines={[]}
                canRemove={canRemoveSeries(one)}
                onRemove={(target) => void removeSeries(target)}
              />
            ))}
            <ParameterSetsSection materialId={id} />
          </TabsContent>
          <TabsContent value="sources" className="mt-3">
            <SourcesTable values={values} />
          </TabsContent>
          <TabsContent value="values" className="mt-3">
            <CatalogValueTable
              values={values}
              units={units}
              canRemove={canRemove}
              onRemove={(value) => void remove(value)}
            />
          </TabsContent>
        </Tabs>
      )}

      {item && <AdoptDialog detail={item} open={adopting} onClose={() => setAdopting(false)} />}
      {item && (
        <AddValueDialog
          detail={item}
          open={adding}
          onClose={() => setAdding(false)}
          onDone={(message) => {
            setAdding(false)
            setAdded(message)
            detail.reload()
          }}
        />
      )}
      {item && (
        <SeriesDialog
          detail={item}
          open={addingSeries}
          onClose={() => setAddingSeries(false)}
          onDone={(message) => {
            setAddingSeries(false)
            setAdded(message)
            detail.reload()
            openTab('curves')
          }}
        />
      )}
      {item && (
        <CreateMaterialDialog detail={item} open={creating} onClose={() => setCreating(false)} />
      )}
    </div>
  )
}
