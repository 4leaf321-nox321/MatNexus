/**
 * 시편 규격의 치수 — **규격은 이름이 아니라 치수 한 벌이다.**
 *
 * `ASTM E8 subsize` 는 게이지 길이 25 mm · 평행부 폭 6 mm 를 뜻한다. 그걸
 * 어디에도 안 적어 두면 사람이 규격서를 펴 놓고 시편마다 옮겨 적고, 그러다 한
 * 건이 틀리면 응력이 통째로 어긋나는데 숫자는 그럴듯해 보인다.
 *
 * ## 칸을 여기 적지 않는다
 *
 * **시험 종류가 자기 규격의 칸을 선언한다.** 인장 규격에는 어깨 반경이 있고
 * DMA 규격에는 지지 간격이 있다 — 하나의 고정된 칸 목록으로 둘을 담으면 절반이
 * 늘 비고, 그 빈 칸이 "안 쟀다" 인지 "이 규격에 없는 값" 인지 구별되지 않는다.
 *
 * 그래서 종류를 고르면 서버에 칸을 물어서 폼을 그린다. 목록을 화면에 적으면
 * 시험 종류를 추가할 때 두 곳을 고쳐야 하고, 그러면 한 곳을 빠뜨린다(D7).
 *
 * ## 저장은 SI, 화면은 mm
 *
 * 규격서는 mm 로 적혀 있고 사람도 mm 로 읽는다. `0.025` 를 치라고 하면 누군가
 * `25` 를 치고, 그러면 변형률이 1000배 틀린다 — 처리 화면과 같은 규칙이다.
 */

import { useEffect, useState } from 'react'

import { vocabularyApi } from '@/modules/vocabulary/api'
import type { SpecimenField, Term } from '@/modules/vocabulary/api'
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
import { display, fromDisplay, toDisplay } from '@/shared/units'
import { useResource } from '@/shared/hooks/useResource'

interface Props {
  slug: string
  term: Term
  onClose: () => void
  onSaved: (term: Term) => void
}

/** 화면 단위의 문자열 → SI 숫자. 빈 칸은 안 보낸다(= 그 치수는 없다). */
function toSi(text: string, field: SpecimenField): number | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const value = Number(trimmed)
  if (!Number.isFinite(value)) return null
  return fromDisplay(value, field.si_unit, field.dimension)
}

export function SpecimenStandardDialog({ slug, term, onClose, onSaved }: Props) {
  const kinds = useResource(() => vocabularyApi.kinds(slug), [slug])
  const [kind, setKind] = useState<string | null>(term.kind ?? null)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const fields = useResource<SpecimenField[]>(
    () => (kind ? vocabularyApi.specimenFields(slug, kind) : Promise.resolve([])),
    [slug, kind]
  )

  useEffect(() => {
    // 종류를 바꾸면 칸이 통째로 바뀐다. **예전 종류의 값을 들고 넘어가지
    // 않는다** — 서버도 그것을 거절한다(스키마 밖의 값이라서).
    if (kind !== (term.kind ?? null)) {
      setDraft({})
      return
    }
    const shown: Record<string, string> = {}
    for (const [key, value] of Object.entries(term.attributes ?? {})) {
      const field = (fields.data ?? []).find((item) => item.key === key)
      if (!field) continue
      shown[key] = String(
        Number(toDisplay(Number(value), field.si_unit, field.dimension).toPrecision(10))
      )
    }
    setDraft(shown)
  }, [kind, term, fields.data])

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const attributes: Record<string, number> = {}
      for (const field of fields.data ?? []) {
        const value = toSi(draft[field.key] ?? '', field)
        if (value !== null) attributes[field.key] = value
      }
      const saved = await vocabularyApi.update(slug, term.id, {
        // 빈 문자열이면 종류를 뗀다 — 그러면 서버가 속성도 함께 비운다.
        kind: kind ?? '',
        attributes,
      })
      onSaved(saved)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{term.value} — 치수</DialogTitle>
          <DialogDescription>
            <b>규격은 이름이 아니라 치수 한 벌입니다.</b> 여기 적어 두면 시편마다 규격서를
            펴 놓고 옮겨 적지 않아도 됩니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={kinds.error ?? fields.error ?? error} />

        <div className="space-y-1.5">
          <Label className="text-xs">시험 종류</Label>
          {/* **종류가 칸을 정한다.** 인장 규격과 DMA 규격은 갖는 치수가 다르다. */}
          <div className="flex flex-wrap gap-1.5">
            {(kinds.data ?? []).map((item) => (
              <Button
                key={item.key}
                size="sm"
                variant={kind === item.key ? 'default' : 'outline'}
                className="h-7 text-xs"
                onClick={() => setKind(item.key)}
              >
                {item.label}
              </Button>
            ))}
            {kind && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={() => setKind(null)}
              >
                종류 없음
              </Button>
            )}
          </div>
        </div>

        {kind === null ? (
          <p className="text-muted-foreground rounded-md border p-4 text-sm">
            종류를 고르면 그 시험의 규격이 갖는 치수 칸이 나옵니다. 종류 없이 이름만 두는
            것도 됩니다 — <b>치수를 모른 채 규격 이름부터 적는 일이 실제로 있습니다.</b>
          </p>
        ) : (
          <div className="space-y-2">
            {(fields.data ?? []).map((field) => {
              const shown = display(field.si_unit, field.dimension)
              return (
                <div key={field.key} className="grid grid-cols-[10rem_1fr] items-start gap-2">
                  <Label className="pt-1.5 text-xs">
                    {field.label}
                    {shown.unit && <span className="text-muted-foreground ml-1">({shown.unit})</span>}
                    {field.is_required && <span className="text-destructive ml-0.5">*</span>}
                  </Label>
                  <div>
                    <Input
                      aria-label={field.label}
                      inputMode="decimal"
                      className="h-8"
                      value={draft[field.key] ?? ''}
                      onChange={(event) =>
                        setDraft((current) => ({ ...current, [field.key]: event.target.value }))
                      }
                    />
                    {field.help && (
                      <p className="text-muted-foreground mt-0.5 text-xs">{field.help}</p>
                    )}
                  </div>
                </div>
              )
            })}
            {(fields.data ?? []).length === 0 && !fields.loading && (
              <p className="text-muted-foreground text-sm">
                이 시험 종류는 아직 규격 치수 칸을 선언하지 않았습니다.
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
          <Button onClick={() => void save()} disabled={busy}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
