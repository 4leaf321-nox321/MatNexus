/**
 * 문헌 **곡선 · 표 한 벌** 넣기(2026-10-22, ADR 0067) — 엑셀에서 축과 열을 복사해 붙여넣는다.
 *
 * 전에는 값 하나씩 넣는 창뿐이라, 온도별 영률 여섯 점이면 여섯 번 넣었고 그것이 한 곡선이라는
 * 사실은 남지 않았다. 규칙은 서버가 지킨다 — 여기는 칸을 채워 줄 뿐:
 *
 *   물성 열   이름으로 찾는다(최대 셋). 단위가 다르면 서버가 정의 단위로 환산한다.
 *   축        고른 물성들의 조건축 가운데 하나 — 같은 온도를 temperature_c · _k 둘로 적지 않게
 *   붙여넣기  축 · 열 차례의 칸. 빈 칸은 그 열의 값이 없는 줄
 *   미리보기  넣을 때와 같은 검사를 서버가 돌리고 되돌린다 — 저장될 점을 그래프로 본다
 */

import { Loader2, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { TIER_LABELS, catalogApi } from '@/modules/catalog/api'
import type {
  CatalogMaterialDetail,
  CatalogSeriesCreate,
  CatalogSeriesCreated,
  PropertyCandidate,
} from '@/modules/catalog/api'
import {
  METHODS,
  SELECT,
  SOURCE_KINDS,
  UNGROUNDED,
  parseConditions,
  parseRows,
} from '@/modules/catalog/catalogForms'
import { axisName, axisUnit } from '@/modules/catalog/catalogShape'
import { CurveChart } from '@/modules/tests/CurveChart'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Textarea } from '@/shared/components/ui/textarea'
import { axisLabel, display, toDisplay } from '@/shared/units'

/** 한 벌의 물성 열 상한 — 저장 · 탄성률 · tan δ 셋이면 DMA 표 하나다. */
const MAX_COLUMNS = 3

interface Column {
  property: PropertyCandidate
  unit: string
}

function PropertySearch({ onPick }: { onPick: (one: PropertyCandidate) => void }) {
  const [query, setQuery] = useState('')
  const [candidates, setCandidates] = useState<PropertyCandidate[]>([])
  useEffect(() => {
    const needle = query.trim()
    if (needle.length < 1) {
      setCandidates([])
      return
    }
    let alive = true
    const timer = setTimeout(() => {
      catalogApi
        .resolveProperty(needle)
        .then((got) => {
          if (alive) setCandidates(got.candidates.filter((one) => !one.deprecated))
        })
        .catch(() => {
          if (alive) setCandidates([])
        })
    }, 200)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [query])
  return (
    <div className="space-y-1">
      <Input
        aria-label="곡선 물성 찾기"
        placeholder="물성 이름으로 찾기 — 탄성계수, 변형률별 인장응력…"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      {candidates.length > 0 && (
        <ul className="max-h-40 overflow-y-auto rounded-md border">
          {candidates.map((one) => (
            <li key={one.key}>
              <button
                type="button"
                className="hover:bg-muted flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm"
                onClick={() => {
                  onPick(one)
                  setQuery('')
                }}
              >
                <span className="font-medium">{one.name}</span>
                <span className="text-muted-foreground font-mono">{one.key}</span>
                <span className="text-muted-foreground ml-auto">{one.si_unit}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** 고른 물성들이 함께 가진 조건축 — 축이 비어 있는 정의는 막지 않는다(서버와 같은 규칙). */
function sharedAxes(columns: Column[]): string[] {
  const listed = columns.map((one) => one.property.condition_axes ?? []).filter((axes) => axes.length > 0)
  if (listed.length === 0) return []
  return listed.reduce((left, right) => left.filter((axis) => right.includes(axis)))
}

export function SeriesDialog({
  detail,
  open,
  onClose,
  onDone,
}: {
  detail: CatalogMaterialDetail
  open: boolean
  onClose: () => void
  onDone: (message: string) => void
}) {
  const [label, setLabel] = useState('')
  const [columns, setColumns] = useState<Column[]>([])
  const [xKey, setXKey] = useState('')
  const [xUnit, setXUnit] = useState('')
  const [pasted, setPasted] = useState('')
  const [shared, setShared] = useState('')
  const [method, setMethod] = useState('digitized')
  const [tier, setTier] = useState(2)
  const [sourceKind, setSourceKind] = useState('journal')
  const [title, setTitle] = useState('')
  const [year, setYear] = useState('')
  const [doi, setDoi] = useState('')
  const [url, setUrl] = useState('')
  const [where, setWhere] = useState('')
  const [preview, setPreview] = useState<CatalogSeriesCreated | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    if (UNGROUNDED.has(method)) setTier(4)
  }, [method])

  const axes = sharedAxes(columns)
  // 축은 고른 물성들의 조건축 가운데서 — 온도가 있으면 온도가 기본이다.
  useEffect(() => {
    if (axes.length === 0 || axes.includes(xKey)) return
    const first = axes.includes('temperature_k') ? 'temperature_k' : axes[0]
    setXKey(first)
    setXUnit(display(axisUnit(first)).unit)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [axes.join('|')])

  const parsed = useMemo(() => {
    try {
      return { rows: parseRows(pasted), problem: null as string | null }
    } catch (caught) {
      return { rows: [], problem: caught instanceof Error ? caught.message : '읽지 못했습니다.' }
    }
  }, [pasted])

  const payload = useMemo<CatalogSeriesCreate | null>(() => {
    if (columns.length === 0 || !xKey.trim()) return null
    return {
      kind: 'curve',
      label: label.trim() || `${columns[0].property.name} — ${axisName(xKey)}별`,
      x_key: xKey.trim(),
      x_unit: xUnit.trim() || null,
      columns: columns.map((one) => ({ property_key: one.property.key, unit: one.unit.trim() || null })),
      rows: parsed.rows,
      conditions: shared.trim() ? parseConditions(shared) : null,
      method,
      quality_tier: tier,
      source: {
        kind: sourceKind,
        title: title.trim() || null,
        year: year.trim() ? Number(year) : null,
        doi: doi.trim() || null,
        url: url.trim() || null,
      },
      source_detail: where.trim() || null,
    }
  }, [columns, xKey, xUnit, label, parsed.rows, shared, method, tier, sourceKind, title, year, doi, url, where])

  // 칸을 바꾸면 미리보기는 낡는다 — 낡은 그림을 보고 저장하지 않게 지운다.
  useEffect(() => setPreview(null), [payload])

  const hasSource = Boolean(title.trim() || doi.trim() || url.trim())
  const ready = payload !== null && parsed.rows.length >= 2 && !parsed.problem && hasSource

  function reset() {
    setLabel('')
    setColumns([])
    setXKey('')
    setXUnit('')
    setPasted('')
    setShared('')
    setMethod('digitized')
    setTier(2)
    setSourceKind('journal')
    setTitle('')
    setYear('')
    setDoi('')
    setUrl('')
    setWhere('')
    setPreview(null)
    setError(null)
  }

  async function run(save: boolean) {
    if (!payload) return
    setBusy(true)
    setError(null)
    try {
      if (save) {
        const made = await catalogApi.createSeries(detail.id, payload)
        reset()
        onDone(`곡선 「${made.series.label}」 을 넣었습니다 — 점 ${made.series.point_count}개.`)
      } else {
        setPreview(await catalogApi.previewSeries(detail.id, payload))
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('넣지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const first = preview?.series.columns[0]
  const chart: [number, number][] =
    preview && first
      ? preview.points
          .filter((one) => one.property_key === first.property_key && one.x != null)
          .map((one) => [toDisplay(one.x as number, axisUnit(xKey)), toDisplay(one.value, first.unit)])
      : []

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          reset()
          onClose()
        }
      }}
    >
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>곡선 · 표 입력 — {detail.name}</DialogTitle>
          <DialogDescription>
            문헌의 곡선이나 표를 한 벌로 넣습니다. 점마다 문헌 값 한 줄이 되고, 출처 · 등급 · 방법은
            벌 전체가 하나입니다.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3">
          <div className="grid gap-1">
            <Label htmlFor="series-label">이름</Label>
            <Input
              id="series-label"
              placeholder="예: 25 °C 공칭 응력-변형률 (Fig. 4)"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label>물성 열 (최대 {MAX_COLUMNS})</Label>
            {columns.map((one, index) => (
              <div key={one.property.key} className="flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm">
                <span className="font-medium">{one.property.name}</span>
                <span className="text-muted-foreground font-mono">{one.property.key}</span>
                <Input
                  aria-label={`${one.property.name} 단위`}
                  className="ml-auto h-7 w-28 font-mono"
                  value={one.unit}
                  onChange={(event) =>
                    setColumns((current) =>
                      current.map((column, at) => (at === index ? { ...column, unit: event.target.value } : column))
                    )
                  }
                />
                <button
                  type="button"
                  aria-label={`${one.property.name} 열 빼기`}
                  className="text-muted-foreground hover:text-foreground"
                  onClick={() => setColumns((current) => current.filter((_, at) => at !== index))}
                >
                  <X className="size-3.5" />
                </button>
              </div>
            ))}
            {columns.length < MAX_COLUMNS && (
              <PropertySearch
                onPick={(one) =>
                  setColumns((current) =>
                    current.some((column) => column.property.key === one.key)
                      ? current
                      : [...current, { property: one, unit: display(one.si_unit || '1').unit || one.si_unit || '1' }]
                  )
                }
              />
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1">
              <Label htmlFor="series-axis">축</Label>
              {axes.length > 0 ? (
                <select
                  id="series-axis"
                  className={SELECT}
                  value={xKey}
                  onChange={(event) => {
                    setXKey(event.target.value)
                    setXUnit(display(axisUnit(event.target.value)).unit)
                  }}
                >
                  {axes.map((axis) => (
                    <option key={axis} value={axis}>
                      {axisName(axis)} ({axis})
                    </option>
                  ))}
                </select>
              ) : (
                <Input
                  id="series-axis"
                  className="font-mono"
                  placeholder="조건 칸 이름 — temperature_k"
                  value={xKey}
                  onChange={(event) => setXKey(event.target.value)}
                />
              )}
            </div>
            <div className="grid gap-1">
              <Label htmlFor="series-axis-unit">축 단위</Label>
              <Input
                id="series-axis-unit"
                className="font-mono"
                placeholder="비우면 축 키의 단위"
                value={xUnit}
                onChange={(event) => setXUnit(event.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-1">
            <Label htmlFor="series-rows">값 붙여넣기 — 축, {columns.map((one) => one.property.name).join(', ') || '물성'} 차례</Label>
            <Textarea
              id="series-rows"
              className="h-36 font-mono"
              placeholder={'25\t200\n100\t190\n200\t180'}
              value={pasted}
              onChange={(event) => setPasted(event.target.value)}
            />
            <p className="text-muted-foreground text-xs">
              {parsed.problem ?? `${parsed.rows.length}줄 읽음 — 엑셀에서 복사한 칸을 그대로 붙여넣으면 됩니다. 빈 칸은 그 열의 값이 없는 줄.`}
            </p>
          </div>

          <div className="grid gap-1">
            <Label htmlFor="series-shared">공통 조건 (선택)</Label>
            <Input
              id="series-shared"
              className="font-mono"
              placeholder="frequency_hz=1, strain_rate_s=0.001"
              value={shared}
              onChange={(event) => setShared(event.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1">
              <Label htmlFor="series-method">방법</Label>
              <select id="series-method" className={SELECT} value={method} onChange={(event) => setMethod(event.target.value)}>
                {METHODS.map(([value, name]) => (
                  <option key={value} value={value}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="series-tier">등급</Label>
              <select
                id="series-tier"
                className={SELECT}
                value={tier}
                disabled={UNGROUNDED.has(method)}
                onChange={(event) => setTier(Number(event.target.value))}
              >
                {[1, 2, 3, 4].map((one) => (
                  <option key={one} value={one}>
                    {one} · {TIER_LABELS[one]}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <fieldset className="grid gap-2 rounded-md border p-3">
            <legend className="px-1 text-sm font-medium">출처 (제목 · DOI · URL 중 하나는 필수)</legend>
            <div className="grid grid-cols-[8rem_1fr_6rem] gap-2">
              <select aria-label="출처 종류" className={SELECT} value={sourceKind} onChange={(event) => setSourceKind(event.target.value)}>
                {SOURCE_KINDS.map(([value, name]) => (
                  <option key={value} value={value}>
                    {name}
                  </option>
                ))}
              </select>
              <Input aria-label="출처 제목" placeholder="제목" value={title} onChange={(event) => setTitle(event.target.value)} />
              <Input aria-label="출처 연도" placeholder="연도" inputMode="numeric" value={year} onChange={(event) => setYear(event.target.value)} />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <Input aria-label="DOI" placeholder="DOI" value={doi} onChange={(event) => setDoi(event.target.value)} />
              <Input aria-label="URL" placeholder="URL" value={url} onChange={(event) => setUrl(event.target.value)} />
              <Input aria-label="출처 안의 위치" placeholder="Fig. 4 · 표 3" value={where} onChange={(event) => setWhere(event.target.value)} />
            </div>
          </fieldset>

          {preview && (
            <div className="space-y-1 rounded-md border p-3">
              <p className="text-sm">
                점 {preview.points.length}개를 넣습니다
                {(preview.converted ?? []).length > 0 ? ` — ${(preview.converted ?? []).join(' · ')}` : ''}.
              </p>
              {first && chart.length > 0 && (
                <CurveChart
                  points={chart}
                  pointsLabel={first.property_name}
                  xLabel={axisLabel(axisName(xKey), axisUnit(xKey))}
                  yLabel={axisLabel(first.property_name, first.unit)}
                  height={220}
                />
              )}
            </div>
          )}

          <ErrorNotice error={error} />
        </div>

        <DialogFooter>
          <Button variant="outline" disabled={!ready || busy} onClick={() => void run(false)}>
            미리보기
          </Button>
          <Button disabled={!ready || busy || preview === null} onClick={() => void run(true)}>
            {busy && <Loader2 className="size-4 animate-spin" />}
            넣기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
