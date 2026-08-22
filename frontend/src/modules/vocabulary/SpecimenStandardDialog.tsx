/**
 * 시편 규격의 치수 — **규격은 이름이 아니라 치수 한 벌이다.**
 *
 * `ASTM E8 subsize` 는 게이지 길이 25 mm · 평행부 폭 6 mm 를 뜻한다. 그걸
 * 어디에도 안 적어 두면 사람이 규격서를 펴 놓고 시편마다 옮겨 적고, 그러다 한
 * 건이 틀리면 응력이 통째로 어긋나는데 숫자는 그럴듯해 보인다.
 *
 * ## 칸이 두 층이다
 *
 *   분류의 기본 칸   그 분류의 규격이면 **예외 없이** 갖는 것
 *   이 규격의 추가 칸  이 규격만 갖는 것
 *
 * **같은 시험 안에서도 시편에 따라 칸이 갈리기 때문이다.** 인장 평판은 폭·두께를
 * 갖고 환봉은 직경을 갖는다. DMA 3점 굽힘에는 지지 간격이 있고 인장 필름에는
 * 없다(실측: DMA 실파일 172개 전부에 장비가 적은 `Geometry name` 이 있고 155개가
 * 3점 굽힘이었다).
 *
 * 분류의 기본 칸으로만 담으면 절반이 늘 비고, 그 빈 칸이 "안 쟀다" 인지 "이
 * 규격에 없는 값" 인지 구별되지 않는다.
 *
 * ## 저장은 SI, 화면은 mm
 *
 * 규격서는 mm 로 적혀 있고 사람도 mm 로 읽는다. `0.025` 를 치라고 하면 누군가
 * `25` 를 치고, 그러면 변형률이 1000배 틀린다 — 처리 화면과 같은 규칙이다.
 */

import { useEffect, useState } from 'react'
import { Ruler } from 'lucide-react'

import { SpecimenFieldsDialog } from '@/modules/vocabulary/SpecimenFieldsDialog'
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
  const fields = useResource(() => vocabularyApi.termFields(slug, term.id), [slug, term.id])
  const shapes = useResource(() => vocabularyApi.crossSections(), [])
  const [crossSection, setCrossSection] = useState<string | null>(term.cross_section ?? null)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  /** 이 규격만의 칸을 고치러 들어간 상태. **고치고 싶어지는 자리가 여기다.** */
  const [editingFields, setEditingFields] = useState(false)

  useEffect(() => {
    const shown: Record<string, string> = {}
    for (const [key, value] of Object.entries(term.attributes ?? {})) {
      const field = (fields.data ?? []).find((item) => item.key === key)
      if (!field) continue
      shown[key] = String(
        Number(toDisplay(Number(value), field.si_unit, field.dimension).toPrecision(10))
      )
    }
    setDraft(shown)
  }, [term, fields.data])

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const attributes: Record<string, number> = {}
      for (const field of fields.data ?? []) {
        const value = toSi(draft[field.key] ?? '', field)
        if (value !== null) attributes[field.key] = value
      }
      onSaved(
        await vocabularyApi.update(slug, term.id, {
          attributes,
          // 빈 문자열이면 뗀다 — 그러면 옛 규칙(폭 곱하기 두께)으로 돈다.
          cross_section: crossSection ?? '',
        })
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  if (editingFields) {
    return (
      <SpecimenFieldsDialog
        slug={slug}
        term={term}
        onClose={() => setEditingFields(false)}
        onSaved={() => {
          setEditingFields(false)
          fields.reload()
        }}
      />
    )
  }

  const rows = fields.data ?? []

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

        <ErrorNotice error={fields.error ?? error} />

        {/* **분류는 상위 값이다.** 축 계층 기계를 그대로 쓴다 — 고치는 자리는
            이 창이 아니라 값의 '표기·상위 분류' 다. 여기서는 무엇인지만 말한다. */}
        <p className="text-muted-foreground text-sm">
          분류 <b className="text-foreground">{term.parent_value ?? '없음'}</b>
          {term.parent_value
            ? ' — 그 분류의 기본 칸에 이 규격의 칸이 더해집니다.'
            : ' — 분류를 정하면 그 분류의 기본 칸이 함께 나옵니다.'}
        </p>

        {rows.length === 0 && !fields.loading ? (
          <p className="text-muted-foreground rounded-md border p-4 text-sm">
            아직 칸이 없습니다. 분류를 정하거나, 아래에서 이 규격만의 칸을 만드세요 —{' '}
            <b>치수를 모른 채 규격 이름부터 적는 일이 실제로 있습니다.</b>
          </p>
        ) : (
          <div className="space-y-2">
            {rows.map((field) => {
              const shown = display(field.si_unit, field.dimension)
              return (
                <div key={field.key} className="grid grid-cols-[10rem_1fr] items-start gap-2">
                  <Label className="pt-1.5 text-xs">
                    {field.label}
                    {shown.unit && (
                      <span className="text-muted-foreground ml-1">({shown.unit})</span>
                    )}
                    {field.is_required && <span className="text-destructive ml-0.5">*</span>}
                    {/* 분류가 준 칸인지 이 규격의 칸인지 보인다 — 지우려면 어디로
                        가야 하는지가 달라진다. */}
                    {!field.inherited && (
                      <span className="text-muted-foreground ml-1 text-xs">· 이 규격</span>
                    )}
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
          </div>
        )}

        {/* **단면적은 모양마다 식이 다르다.** 12.5 mm 환봉은 122.7 mm² 인데
            평판 식으로는 그 값이 안 나온다 — 그런데 그 수로 나눈 응력은 오류
            없이 그럴듯하다. */}
        <div className="space-y-1.5">
          <Label className="text-xs">단면적</Label>
          <div className="flex flex-wrap gap-1.5">
            {(shapes.data ?? []).map((shape) => {
              // 그 식이 요구하는 칸이 이 규격에 없으면 못 고른다 — 골라 봐야
              // 늘 실패하고, 사람은 그 이유를 처리 화면에서 만난다.
              const missing = shape.needs.filter(
                (need) => !rows.some((field) => field.key === need)
              )
              return (
                <Button
                  key={shape.key}
                  size="sm"
                  variant={crossSection === shape.key ? 'default' : 'outline'}
                  className="h-7 text-xs"
                  disabled={missing.length > 0}
                  title={
                    missing.length > 0
                      ? `치수 칸 ${missing.join(', ')} 이(가) 없습니다`
                      : (shape.help ?? undefined)
                  }
                  onClick={() => setCrossSection(shape.key)}
                >
                  {shape.label}
                </Button>
              )
            })}
            {crossSection && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={() => setCrossSection(null)}
              >
                안 고름
              </Button>
            )}
          </div>
          {!crossSection && (
            <p className="text-muted-foreground text-xs">
              안 고르면 <b>폭 곱하기 두께</b>로 계산합니다(옛 규칙). 환봉이면 반드시
              고르세요 — 안 그러면 단면적이 안 나오거나 틀립니다.
            </p>
          )}
        </div>

        {/* **칸이 모자라면 여기서 바로 더한다.** "이 규격은 환봉이라 직경이
            필요한데" 는 규격을 적다가 나오는 말이다. */}
        <Button
          size="sm"
          variant="ghost"
          className="h-7 self-start text-xs"
          onClick={() => setEditingFields(true)}
        >
          <Ruler className="size-3.5" />
          이 규격만의 칸
        </Button>

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
