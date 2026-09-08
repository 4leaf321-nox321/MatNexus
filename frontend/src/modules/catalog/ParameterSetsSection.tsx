/**
 * 문헌 재료의 **모델 파라미터 벌** — 낱개가 아니라 묶음으로 보이고, 묶음으로 담는다.
 *
 * Anand 하나에 9개 상수가 들어 있다(ADR 0029). 값 표에 낱개로 흩어 두면 같은 이름이
 * 아홉 번 서고, **`A` 만 담아 봐야 모델이 못 쓴다** — 그래서 여기서 한 벌씩 보여
 * 주고 한 벌씩 담는다.
 *
 * ## 단위를 항마다 적는다
 *
 * 한 벌 안에서 `1`·`1/s`·`MPa`·`K` 가 섞인다. 정의가 말하는 단위(대개 `1`)는
 * 거짓이라 쓰지 않는다.
 *
 * ## 담는 곳은 재료다 — 카드가 아니다
 *
 * 카드에 바로 넣으면 카드를 만들기 전까지 물성 탭에서 안 보이고, 논문마다 다른
 * 벌을 나란히 둘 수 없다(ADR 0029 D3). 재료에 담기면 물성 표에 `문헌 묶음` 으로
 * 한 줄 선다.
 */

import { useEffect, useState } from 'react'
import { Layers, Loader2, PackagePlus } from 'lucide-react'

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { useResource } from '@/shared/hooks/useResource'

type ParameterSet = components['schemas']['CatalogParameterSetOut']
type MaterialOut = components['schemas']['MaterialOut']
type MaterialPage = components['schemas']['Page_MaterialOut_']

/** 값 하나를 사람이 읽을 글자로. **단위가 `1` 이면 안 적는다** — 무차원이다. */
function shown(term: ParameterSet['terms'][number]): string {
  const value = term.value === null || term.value === undefined ? (term.text ?? '?') : term.value
  const unit = term.unit && term.unit !== '1' ? ` ${term.unit}` : ''
  return `${value}${unit}`
}

export function ParameterSetsSection({ materialId }: { materialId: string }) {
  const { data, error } = useResource(
    () => api.get<ParameterSet[]>(`/catalog/materials/${materialId}/parameter-sets`),
    [materialId]
  )
  const [adopting, setAdopting] = useState<ParameterSet | null>(null)
  const sets = data ?? []

  if (error) return <ErrorNotice error={error} />
  if (sets.length === 0) return null

  return (
    <section className="mt-6">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <Layers className="text-muted-foreground size-4" />
        모델 파라미터
        <span className="text-muted-foreground text-xs font-normal">
          {sets.length}벌 · 여럿이 한 벌이어야 뜻이 있는 값입니다
        </span>
      </h2>

      <div className="space-y-3">
        {sets.map((set) => (
          <div key={`${set.property_key}:${set.model}:${set.set_id}`} className="rounded-md border p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">{set.label}</span>
              <Badge variant="secondary">{set.model || '모델 미상'}</Badge>
              {set.set_id && (
                <span className="text-muted-foreground font-mono text-xs">{set.set_id}</span>
              )}
              {set.quality_tier !== null && set.quality_tier !== undefined && (
                <Badge variant="outline">tier{set.quality_tier}</Badge>
              )}
              <Button
                size="sm"
                variant="outline"
                className="ml-auto"
                onClick={() => setAdopting(set)}
              >
                <PackagePlus className="size-4" />
                사내 재료에 담기
              </Button>
            </div>

            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {(set.terms ?? []).map((term) => (
                <span key={term.term} className="tabular-nums">
                  <span className="font-medium">{term.term}</span>
                  <span className="text-muted-foreground"> = {shown(term)}</span>
                </span>
              ))}
            </div>

            {set.source_detail && (
              <p className="text-muted-foreground mt-2 text-xs">{set.source_detail}</p>
            )}
          </div>
        ))}
      </div>

      <AdoptParameterSetDialog
        set={adopting}
        catalogMaterialId={materialId}
        onClose={() => setAdopting(null)}
      />
    </section>
  )
}

/**
 * 한 벌을 어느 사내 재료에 담을지 고른다.
 *
 * **담긴 값은 스냅샷이다** — 카탈로그를 다시 이관해도 조용히 바뀌지 않는다(선언
 * 물성 채우기와 같은 규칙).
 */
function AdoptParameterSetDialog({
  set,
  catalogMaterialId,
  onClose,
}: {
  set: ParameterSet | null
  catalogMaterialId: string
  onClose: () => void
}) {
  const [typed, setTyped] = useState('')
  const [found, setFound] = useState<MaterialOut[]>([])
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<string | null>(null)
  const [failed, setFailed] = useState<Error | null>(null)

  useEffect(() => {
    if (!set) {
      setTyped('')
      setFound([])
      setDone(null)
      setFailed(null)
    }
  }, [set])

  useEffect(() => {
    if (!set || typed.trim().length < 2) {
      setFound([])
      return
    }
    const timer = window.setTimeout(() => {
      api
        .get<MaterialPage>(`/materials?q=${encodeURIComponent(typed.trim())}&limit=8`)
        .then((page) => setFound(page.items))
        .catch(() => setFound([]))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [typed, set])

  async function adopt(target: MaterialOut) {
    if (!set) return
    setBusy(true)
    setFailed(null)
    try {
      await api.post(`/materials/${target.id}/parameter-sets`, {
        property_key: set.property_key,
        catalog_material_id: catalogMaterialId,
        model: set.model,
        set_id: set.set_id,
      })
      setDone(target.record_name)
    } catch (caught) {
      setFailed(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={set !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>사내 재료에 담기</DialogTitle>
          <DialogDescription>
            {set?.label} · {set?.model} — 변수 {set?.terms?.length ?? 0}개를{' '}
            <strong>한 벌로</strong> 담습니다. 담긴 뒤에는 그 재료의 물성 탭에 섭니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={failed} />

        {done ? (
          <p className="text-sm">
            <strong>{done}</strong> 에 담았습니다. 그 재료의 물성 탭에서 확인하세요.
          </p>
        ) : (
          <div className="space-y-3">
            <Input
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              placeholder="사내 재료 이름·번호로 찾기 (두 글자 이상)"
              aria-label="사내 재료 찾기"
              autoFocus
            />
            <ul className="divide-y rounded-md border text-sm">
              {found.length === 0 && (
                <li className="text-muted-foreground px-3 py-2 text-xs">
                  {typed.trim().length < 2 ? '두 글자 이상 입력하세요.' : '찾은 재료가 없습니다.'}
                </li>
              )}
              {found.map((one) => (
                <li key={one.id} className="flex items-center justify-between gap-2 px-3 py-2">
                  <span className="min-w-0 truncate">{one.record_name}</span>
                  <Button type="button" size="sm" disabled={busy} onClick={() => adopt(one)}>
                    {busy ? <Loader2 className="size-4 animate-spin" /> : '담기'}
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
