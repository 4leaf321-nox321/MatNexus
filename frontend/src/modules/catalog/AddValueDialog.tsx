/**
 * 문헌 값 하나 넣기 — **값 · 단위 · 조건 · 방법 · 등급 · 출처가 한 몸이다.**
 *
 * 값 넣기는 MCP·API 로만 됐다(2026-09-12). 데이터시트를 손에 든 사람이 화면에서
 * 바로 넣을 자리다. 규칙은 서버(`contribute.py`)가 지킨다 — 여기는 칸을 채워 줄 뿐:
 *
 *   물성    이름으로 쳐서 찾는다(`resolve`). 폐기된 키는 못 고른다.
 *   단위    정의의 단위가 기본이고, 다르게 적으면 서버가 같은 차원일 때만 환산한다.
 *   출처    제목·DOI·URL 중 하나는 있어야 한다 — 출처 없는 값은 안 받는다.
 *   등급    추정(estimated)·계산(computed)은 tier 4 여야 한다 — 화면이 따라 맞춘다.
 */

import { Loader2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { TIER_LABELS, catalogApi } from '@/modules/catalog/api'
import type { CatalogMaterialDetail, CatalogValueCreate, PropertyCandidate } from '@/modules/catalog/api'
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

const METHODS: [string, string][] = [
  ['handbook', '핸드북·규격'],
  ['measured', '실측(문서에 인쇄된)'],
  ['digitized', '그래프 판독'],
  ['computed', '계산'],
  ['estimated', '추정'],
]
const SOURCE_KINDS: [string, string][] = [
  ['datasheet', '데이터시트'],
  ['journal', '논문'],
  ['book', '책·핸드북'],
  ['standard', '규격'],
  ['database', '데이터베이스'],
  ['web', '웹'],
  ['other', '기타'],
]
/** 근거 없는 방법 — tier 4 여야 서버가 받는다. */
const UNGROUNDED = new Set(['computed', 'estimated'])

const SELECT = 'border-input bg-background h-9 w-full rounded-md border px-2 text-sm'

export function AddValueDialog({
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
  const [query, setQuery] = useState('')
  const [candidates, setCandidates] = useState<PropertyCandidate[]>([])
  const [property, setProperty] = useState<PropertyCandidate | null>(null)
  const [value, setValue] = useState('')
  const [unit, setUnit] = useState('')
  const [temperature, setTemperature] = useState('')
  const [method, setMethod] = useState('handbook')
  const [tier, setTier] = useState(2)
  const [sourceKind, setSourceKind] = useState('datasheet')
  const [title, setTitle] = useState('')
  const [year, setYear] = useState('')
  const [doi, setDoi] = useState('')
  const [url, setUrl] = useState('')
  const [detailWhere, setDetailWhere] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // 이름을 치면 서버가 푼다 — 화면이 정의 목록을 들고 있지 않는다.
  useEffect(() => {
    const needle = query.trim()
    if (!open || property || needle.length < 1) {
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
  }, [query, open, property])

  // 추정·계산은 tier 4 — 사람이 2 로 두고 저장하면 서버가 거절하니 먼저 맞춘다.
  useEffect(() => {
    if (UNGROUNDED.has(method)) setTier(4)
  }, [method])

  function pick(one: PropertyCandidate) {
    setProperty(one)
    setUnit(one.si_unit || '1')
    setQuery('')
  }

  function reset() {
    setQuery('')
    setCandidates([])
    setProperty(null)
    setValue('')
    setUnit('')
    setTemperature('')
    setMethod('handbook')
    setTier(2)
    setSourceKind('datasheet')
    setTitle('')
    setYear('')
    setDoi('')
    setUrl('')
    setDetailWhere('')
    setError(null)
  }

  const hasSource = Boolean(title.trim() || doi.trim() || url.trim())
  const ready = property !== null && value.trim() !== '' && !Number.isNaN(Number(value)) && hasSource

  const payload = useMemo<CatalogValueCreate | null>(() => {
    if (!property) return null
    const conditions: Record<string, unknown> = {}
    if (temperature.trim() !== '' && !Number.isNaN(Number(temperature))) {
      conditions['temperature_k'] = Number((Number(temperature) + 273.15).toFixed(2))
    }
    return {
      property_key: property.key,
      value_num: Number(value),
      unit: unit.trim() || null,
      method,
      quality_tier: tier,
      conditions: Object.keys(conditions).length > 0 ? conditions : null,
      source: {
        kind: sourceKind,
        title: title.trim() || null,
        year: year.trim() ? Number(year) : null,
        doi: doi.trim() || null,
        url: url.trim() || null,
      },
      source_detail: detailWhere.trim() || null,
    }
  }, [property, value, unit, temperature, method, tier, sourceKind, title, year, doi, url, detailWhere])

  async function submit() {
    if (!payload) return
    setSaving(true)
    setError(null)
    try {
      const made = await catalogApi.createValue(detail.id, payload)
      const stored = made.value
      const message = made.converted
        ? `넣었습니다 — ${made.converted}`
        : `넣었습니다 — ${stored.property_name} ${stored.value_num} ${stored.unit ?? ''}`
      reset()
      onDone(message)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('넣지 못했습니다.'))
    } finally {
      setSaving(false)
    }
  }

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
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>문헌 값 넣기 — {detail.name}</DialogTitle>
          <DialogDescription>
            값·단위·조건·방법·등급·출처를 함께 적습니다. 출처 없는 값은 받지 않습니다.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3">
          <div className="space-y-1.5">
            <Label>물성</Label>
            {property ? (
              <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
                <span className="font-medium">{property.name}</span>
                <span className="text-muted-foreground font-mono">{property.key}</span>
                <Button size="sm" variant="ghost" className="ml-auto h-7" onClick={() => setProperty(null)}>
                  바꾸기
                </Button>
              </div>
            ) : (
              <>
                <Input
                  aria-label="물성 찾기"
                  autoFocus
                  placeholder="이름으로 쳐서 찾기 — 항복강도, 열전도율…"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
                {candidates.length > 0 && (
                  <ul className="max-h-48 overflow-y-auto rounded-md border">
                    {candidates.map((one) => (
                      <li key={one.key}>
                        <button
                          type="button"
                          className="hover:bg-muted flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm"
                          onClick={() => pick(one)}
                        >
                          <span className="font-medium">{one.name}</span>
                          <span className="text-muted-foreground font-mono">{one.key}</span>
                          <span className="text-muted-foreground ml-auto">{one.si_unit}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="grid gap-1">
              <Label htmlFor="new-value">값</Label>
              <Input
                id="new-value"
                inputMode="decimal"
                value={value}
                onChange={(event) => setValue(event.target.value)}
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="new-unit">단위</Label>
              <Input
                id="new-unit"
                className="font-mono"
                value={unit}
                placeholder={property?.si_unit || '단위'}
                onChange={(event) => setUnit(event.target.value)}
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="new-temp">온도 (°C)</Label>
              <Input
                id="new-temp"
                inputMode="decimal"
                value={temperature}
                placeholder="23"
                onChange={(event) => setTemperature(event.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1">
              <Label htmlFor="new-method">방법</Label>
              <select
                id="new-method"
                className={SELECT}
                value={method}
                onChange={(event) => setMethod(event.target.value)}
              >
                {METHODS.map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="new-tier">등급</Label>
              <select
                id="new-tier"
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

          <fieldset className="grid gap-3 rounded-md border p-3">
            <legend className="px-1 text-sm font-medium">출처</legend>
            <div className="grid grid-cols-3 gap-3">
              <div className="grid gap-1">
                <Label htmlFor="new-source-kind">종류</Label>
                <select
                  id="new-source-kind"
                  className={SELECT}
                  value={sourceKind}
                  onChange={(event) => setSourceKind(event.target.value)}
                >
                  {SOURCE_KINDS.map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-span-2 grid gap-1">
                <Label htmlFor="new-source-title">제목</Label>
                <Input id="new-source-title" value={title} onChange={(event) => setTitle(event.target.value)} />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="grid gap-1">
                <Label htmlFor="new-source-year">연도</Label>
                <Input
                  id="new-source-year"
                  inputMode="numeric"
                  value={year}
                  onChange={(event) => setYear(event.target.value)}
                />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="new-source-doi">DOI</Label>
                <Input id="new-source-doi" value={doi} onChange={(event) => setDoi(event.target.value)} />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="new-source-url">URL</Label>
                <Input id="new-source-url" value={url} onChange={(event) => setUrl(event.target.value)} />
              </div>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="new-source-detail">출처 안의 위치</Label>
              <Input
                id="new-source-detail"
                value={detailWhere}
                placeholder="표 3 · p. 214 · Fig. 5"
                onChange={(event) => setDetailWhere(event.target.value)}
              />
            </div>
            {!hasSource && (
              <p className="text-muted-foreground text-xs">제목·DOI·URL 중 하나는 있어야 합니다.</p>
            )}
          </fieldset>

          <ErrorNotice error={error} />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => { reset(); onClose() }}>
            취소
          </Button>
          <Button onClick={submit} disabled={!ready || saving}>
            {saving && <Loader2 className="size-4 animate-spin" />}
            넣기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
