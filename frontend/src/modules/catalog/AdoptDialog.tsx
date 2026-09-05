/**
 * 카탈로그에서 채우기 — **문헌 값을 사내 재료의 선언 물성으로 담는다.**
 *
 * 빈 물성칸을 채우는 것이 이 카탈로그의 용도다. 담는 값은 **스냅샷**(복사본)이라
 * 카탈로그를 재이관해도 조용히 바뀌지 않고, 출처·등급이 참고문헌 문자열로
 * 따라간다. tier4(추정·가정)도 똑같이 담을 수 있다 — 배지로 구별만 한다.
 *
 * ## 단위 변환이 없다
 *
 * 카탈로그 값은 SI 로 저장돼 있고, 선언 물성은 `input_unit` 을 비우면 정본 SI 로
 * 받는다. 숫자가 그대로 흐르고, 표기 등가는 백엔드 계약 테스트가 지킨다.
 *
 * ## 선언 물성은 통째 교체라 여기서 병합한다
 *
 * PATCH 의 declared_properties 는 전체 교체다 — 기존 줄을 그대로 되보내고,
 * 담는 항목만 더하거나(없던 것) 바꾼다(이미 있던 것 — 기본은 안 담는다).
 */

import { Loader2, PackagePlus } from 'lucide-react'
import { useEffect, useState } from 'react'

import {
  ADOPTABLE,
  TIER_LABELS,
  adoptionReference,
  adoptionSource,
  fmtValue,
} from '@/modules/catalog/api'
import type { CatalogMaterialDetail, CatalogValue } from '@/modules/catalog/api'
import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
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

type MaterialOut = components['schemas']['MaterialOut']
type MaterialPage = components['schemas']['Page_MaterialOut_']
type DeclaredIn = components['schemas']['DeclaredPropertyIn']

/** 담을 수 있는 값인가 — 매핑에 있고, 수치이며, 서버 제약을 넘지 않는 것. */
function adoptable(value: CatalogValue): boolean {
  const target = ADOPTABLE[value.property_key]
  if (!target || value.value_num === null || value.value_num === undefined) return false
  // 포아송비의 서버 제약(0 ≤ ν < 0.5). 카탈로그에는 음의 포아송비(열분해흑연)가
  // 실재한다 — 그런 값은 기본 칸에 못 담으므로 목록에서 뺀다.
  if (target.place === 'column' && target.field === 'poisson_ratio') {
    return value.value_num >= 0 && value.value_num < 0.5
  }
  if (target.place === 'column' && target.field === 'density') {
    return value.value_num > 0
  }
  return true
}

/** 기존 선언 줄(Out)을 다시 보낼 수 있는 모양(In)으로 — 값은 입력 단위 그대로. */
function resend(row: components['schemas']['DeclaredPropertyOut']): DeclaredIn {
  return {
    item: row.item,
    points: row.points.map((p) => ({ temperature_k: p.temperature_k, value: p.value })),
    input_unit: row.input_unit,
    scale: row.scale,
    source: row.source,
    reference: row.reference,
    note: row.note,
  }
}

export function AdoptDialog({
  detail,
  open,
  onClose,
  fixedTarget,
  onDone,
}: {
  detail: CatalogMaterialDetail
  open: boolean
  onClose: () => void
  /** 사내 재료 상세에서 열 때 — 대상이 정해져 있어 검색 단계를 건너뛴다. */
  fixedTarget?: MaterialOut
  /** 담기가 끝났을 때 — 부모 화면이 재료를 다시 읽는 데 쓴다. */
  onDone?: () => void
}) {
  const [typed, setTyped] = useState('')
  const [found, setFound] = useState<MaterialOut[]>([])
  const [target, setTarget] = useState<MaterialOut | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [doneCount, setDoneCount] = useState<number | null>(null)

  const candidates = detail.values.filter(adoptable)

  useEffect(() => {
    if (!open) {
      setTarget(null)
      setPicked(new Set())
      setDoneCount(null)
      setError(null)
      setTyped('')
      setFound([])
    } else if (fixedTarget) {
      chooseTarget(fixedTarget)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 열릴 때 한 번이면 된다
  }, [open, fixedTarget])

  // 대상 재료 검색 — 250ms 디바운스.
  useEffect(() => {
    if (!open || target) return
    const timer = setTimeout(() => {
      api
        .get<MaterialPage>(`/materials?q=${encodeURIComponent(typed)}&limit=8`)
        .then((page) => setFound(page.items))
        .catch((caught) =>
          setError(caught instanceof Error ? caught : new Error('검색하지 못했습니다.'))
        )
    }, 250)
    return () => clearTimeout(timer)
  }, [typed, open, target])

  /** 이미 그 항목이 있는가 — 있으면 기본으로 안 담는다(담으면 교체). */
  const existingItems = new Set((target?.declared_properties ?? []).map((row) => row.item))
  function taken(value: CatalogValue): boolean {
    const slot = ADOPTABLE[value.property_key]
    if (!slot) return false
    if (slot.place === 'column') {
      return slot.field === 'density' ? target?.density != null : target?.poisson_ratio != null
    }
    return existingItems.has(slot.item)
  }

  function chooseTarget(one: MaterialOut) {
    setTarget(one)
    // 기본 선택: 대표값이면서 대상의 그 칸이 비어 있는 것.
    setPicked(
      new Set(
        candidates
          .filter((value) => value.representative && !isTakenFor(one, value))
          .map((value) => value.id)
      )
    )
  }

  function isTakenFor(one: MaterialOut, value: CatalogValue): boolean {
    const slot = ADOPTABLE[value.property_key]
    if (!slot) return false
    if (slot.place === 'column') {
      return slot.field === 'density' ? one.density != null : one.poisson_ratio != null
    }
    return (one.declared_properties ?? []).some((row) => row.item === slot.item)
  }

  async function apply() {
    if (!target) return
    setBusy(true)
    setError(null)
    try {
      const chosen = candidates.filter((value) => picked.has(value.id))

      // 선언 항목별로 묶는다 — 항목 하나가 온도점 여러 개를 든다.
      const byItem = new Map<string, CatalogValue[]>()
      const patch: Record<string, unknown> = {}
      for (const value of chosen) {
        const slot = ADOPTABLE[value.property_key]
        if (!slot) continue
        if (slot.place === 'column') {
          if (slot.field === 'density') {
            patch.density = value.value_num
            patch.density_unit = 'kg/m3'
          } else {
            patch.poisson_ratio = value.value_num
          }
          continue
        }
        const list = byItem.get(slot.item) ?? []
        list.push(value)
        byItem.set(slot.item, list)
      }

      if (byItem.size > 0) {
        const newRows: DeclaredIn[] = [...byItem.entries()].map(([item, values]) => {
          const seen = new Set<number | null>()
          const points = values
            .map((value) => ({
              temperature_k:
                typeof value.conditions?.['temperature_k'] === 'number'
                  ? (value.conditions['temperature_k'] as number)
                  : null,
              value: value.value_num as number,
            }))
            .filter((point) => {
              if (seen.has(point.temperature_k)) return false
              seen.add(point.temperature_k)
              return true
            })
            .sort((a, b) => (a.temperature_k ?? -1) - (b.temperature_k ?? -1))
          return {
            item,
            points,
            // input_unit 비움 = 정본 SI — 카탈로그 값이 이미 SI 라 변환이 없다.
            source: adoptionSource(values[0]),
            reference: values.map(adoptionReference).join(' / '),
            note: '문헌 물성 카탈로그에서 채택 (스냅샷)',
          }
        })
        const kept = (target.declared_properties ?? [])
          .filter((row) => !byItem.has(row.item))
          .map(resend)
        patch.declared_properties = [...kept, ...newRows]
      }

      await api.patch<MaterialOut>(`/materials/${target.id}`, patch)
      setDoneCount(chosen.length)
      onDone?.()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('담지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>「{detail.name}」 의 값을 사내 재료에 채우기</DialogTitle>
          <DialogDescription>
            담은 값은 복사본(스냅샷)이고 출처·등급이 함께 적힙니다. 카탈로그가
            갱신돼도 담은 값은 바뀌지 않습니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <ErrorNotice error={error} />

          {doneCount !== null ? (
            <p className="text-sm">
              <b className="text-emerald-700 dark:text-emerald-500">담았습니다.</b> {doneCount}건이
              「{target?.record_name}」 에 들어갔습니다 — 재료 상세의 물성 탭에서 확인하세요.
            </p>
          ) : !target ? (
            <>
              <Input
                aria-label="사내 재료 검색"
                placeholder="어느 재료에 담을까요 — 이름으로 검색"
                value={typed}
                onChange={(event) => setTyped(event.target.value)}
              />
              <div className="space-y-1">
                {found.map((one) => (
                  <button
                    key={one.id}
                    type="button"
                    className="hover:bg-muted block w-full rounded-md border px-3 py-2 text-left text-sm"
                    onClick={() => chooseTarget(one)}
                  >
                    {one.record_name}
                    {one.alias && (
                      <span className="text-muted-foreground ml-2 text-xs">{one.alias}</span>
                    )}
                  </button>
                ))}
                {typed && found.length === 0 && (
                  <p className="text-muted-foreground text-xs">검색 결과가 없습니다.</p>
                )}
              </div>
            </>
          ) : (
            <>
              <p className="text-sm">
                대상: <b>{target.record_name}</b>
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-2"
                  onClick={() => setTarget(null)}
                  disabled={busy}
                >
                  바꾸기
                </Button>
              </p>
              {candidates.length === 0 && (
                <p className="text-muted-foreground text-sm">
                  이 재료에는 담을 수 있는 물성(매핑된 10종)이 없습니다.
                </p>
              )}
              <div className="space-y-1">
                {candidates.map((value) => {
                  const slot = ADOPTABLE[value.property_key]
                  const already = taken(value)
                  return (
                    <label
                      key={value.id}
                      className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm"
                    >
                      <input
                        type="checkbox"
                        className="accent-primary size-4"
                        checked={picked.has(value.id)}
                        onChange={(event) => {
                          const checked = event.target.checked
                          setPicked((now) => {
                            const next = new Set(now)
                            if (checked) next.add(value.id)
                            else next.delete(value.id)
                            return next
                          })
                        }}
                      />
                      <span className="min-w-24 font-medium">{slot?.item}</span>
                      <span className="tabular-nums">{fmtValue(value.value_num, value.unit)}</span>
                      <span className="text-muted-foreground text-xs">
                        {TIER_LABELS[value.quality_tier] ?? `t${value.quality_tier}`}
                        {value.representative && value.n_candidates > 1 && ' · 대표값'}
                        {!value.representative && ' · 대안'}
                      </span>
                      {already && (
                        <span className="text-xs text-amber-700 dark:text-amber-500">
                          이미 있음 — 담으면 교체
                        </span>
                      )}
                    </label>
                  )
                })}
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {doneCount !== null ? '닫기' : '취소'}
          </Button>
          {doneCount === null && target && (
            <Button onClick={() => void apply()} disabled={busy || picked.size === 0}>
              {busy ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <PackagePlus className="size-4" />
              )}
              {picked.size}건 담기
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
