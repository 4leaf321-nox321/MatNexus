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
import { Plus, Ruler, Trash2 } from 'lucide-react'

import { SpecimenFieldsDialog } from '@/modules/vocabulary/SpecimenFieldsDialog'
import { vocabularyApi } from '@/modules/vocabulary/api'
import type {
  CrossSection,
  RatioCheck,
  SpecimenField,
  Term,
} from '@/modules/vocabulary/api'
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

/** 빈 칸은 `null`. `Number('')` 이 0 이 되어 "최소 0" 이 되면 안 된다. */
function numberOrNull(text: string): number | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const value = Number(trimmed)
  return Number.isFinite(value) ? value : null
}

/** 이 칸이 담는 것이 숫자인가. 문자·선택은 단위도 환산도 없다. */
const isNumber = (field: SpecimenField) => (field.kind ?? 'number') === 'number'

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
  /** 식을 고르느라 방금 만든 칸. 값을 적어야 한다는 것을 말해 준다. */
  const [added, setAdded] = useState<string[]>([])
  /**
   * 이 규격이 요구하는 **비율 조건.**
   *
   * 규격이 치수를 안 주고 비만 주는 일이 흔하다 — DMA 는 숫자를 실제로 주는
   * 파트가 셋뿐이고 나머지는 전부 비율이거나 장비 위임이다.
   */
  const [checks, setChecks] = useState<RatioCheck[]>(term.ratio_checks ?? [])

  useEffect(() => {
    const shown: Record<string, string> = {}
    for (const [key, value] of Object.entries(term.attributes ?? {})) {
      const field = (fields.data ?? []).find((item) => item.key === key)
      if (!field) continue
      shown[key] = isNumber(field)
        ? String(Number(toDisplay(Number(value), field.si_unit, field.dimension).toPrecision(10)))
        : String(value)
    }
    setDraft(shown)
  }, [term, fields.data])

  /**
   * 식을 고른다. **없는 칸은 대신 만든다.**
   *
   * 전에는 요구 칸이 없으면 버튼을 회색으로 두고 무엇이 없는지 적었다. 그 말만
   * 보고는 할 일을 알 수 없었다 — `outer_diameter` 는 우리 내부 이름이고, 칸을
   * 만들려면 창을 하나 더 열어 이름·키·차원을 직접 채워야 했다. 식이 자기가
   * 요구하는 칸이 **어떤 칸인지**(이름·차원·저장 단위) 알고 있으므로 여기서
   * 만들면 된다.
   */
  async function choose(shape: CrossSection) {
    const missing = shape.needs.filter((need) => !rows.some((field) => field.key === need.key))
    if (missing.length === 0) {
      setCrossSection(shape.key)
      return
    }
    setBusy(true)
    setError(null)
    try {
      // 이 규격이 직접 가진 칸에 더한다. 위에서 온 칸은 여기서 못 고친다.
      const mine = rows
        .filter((field) => !field.inherited)
        .map(({ inherited: _inherited, ...field }) => field)
      await vocabularyApi.update(slug, term.id, {
        extra_fields: [
          ...mine,
          ...missing.map((need) => ({
            key: need.key,
            label: need.label,
            kind: 'number',
            choices: [],
            symbol: null,
            dimension: need.dimension,
            si_unit: need.si_unit,
            is_required: false,
            help: null,
          })),
        ],
      })
      setAdded(missing.map((need) => need.label))
      setCrossSection(shape.key)
      fields.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('칸을 만들지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const attributes: Record<string, number | string> = {}
      for (const field of fields.data ?? []) {
        if (!isNumber(field)) {
          const text = (draft[field.key] ?? '').trim()
          if (text) attributes[field.key] = text
          continue
        }
        const value = toSi(draft[field.key] ?? '', field)
        if (value !== null) attributes[field.key] = value
      }
      onSaved(
        await vocabularyApi.update(slug, term.id, {
          ratio_checks: checks.filter((one) => one.numerator && one.denominator),
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
        editsBase={false}
        onClose={() => setEditingFields(false)}
        onSaved={() => {
          setEditingFields(false)
          fields.reload()
        }}
      />
    )
  }

  const rows = fields.data ?? []
  /** 비를 잴 수 있는 칸은 숫자 칸뿐이다. */
  const numbers = rows.filter(isNumber)

  function patchCheck(index: number, change: Partial<RatioCheck>) {
    setChecks((now) => now.map((one, at) => (at === index ? { ...one, ...change } : one)))
  }

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
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
            : ' — 분류를 정하면 그 분류의 기본 칸(인장이면 게이지 길이 …)이 함께 나옵니다. 값 목록에서 이 값을 눌러 상위 분류를 정하세요.'}
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
                    {/* **도면은 글자로 적혀 있다.** 시편을 발주할 때 사람이 보는
                        것도 그 글자다 — 같은 D 가 규격마다 다른 뜻이라 함께 보여
                        주지 않으면 옮겨 적다가 틀린다. */}
                    {field.symbol && (
                      <span className="ml-1 font-mono font-semibold">{field.symbol}</span>
                    )}
                    {isNumber(field) && shown.unit && (
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
                    {field.kind === 'choice' ? (
                      <select
                        aria-label={field.label}
                        className="border-input bg-background h-8 w-full rounded-md border px-2 text-sm"
                        value={draft[field.key] ?? ''}
                        onChange={(event) =>
                          setDraft((current) => ({ ...current, [field.key]: event.target.value }))
                        }
                      >
                        <option value="">— 안 고름 —</option>
                        {field.choices.map((one) => (
                          <option key={one} value={one}>
                            {one}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <Input
                        aria-label={field.label}
                        inputMode={isNumber(field) ? 'decimal' : 'text'}
                        className="h-8"
                        value={draft[field.key] ?? ''}
                        onChange={(event) =>
                          setDraft((current) => ({ ...current, [field.key]: event.target.value }))
                        }
                      />
                    )}
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
            {(shapes.data ?? []).map((shape) => (
              <Button
                key={shape.key}
                size="sm"
                variant={crossSection === shape.key ? 'default' : 'outline'}
                className="h-7 text-xs"
                disabled={busy}
                title={shape.help ?? undefined}
                onClick={() => void choose(shape)}
              >
                {shape.label}
              </Button>
            ))}
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
          {/* **설명 대신 실행.** 전에는 "칸이 없어 못 고릅니다" 를 다섯 줄로
              적었는데, 그 말만 보고는 할 일을 알 수 없었다. */}
          {added.length > 0 ? (
            <p className="text-xs">
              <b>{added.join(' · ')}</b> 칸을 만들었습니다 — 위에 값을 적으세요.
            </p>
          ) : (
            <p className="text-muted-foreground text-xs">
              고르면 <b>필요한 칸이 함께 생깁니다</b>. 안 고르면 폭 곱하기 두께로
              계산합니다(옛 규칙) — 환봉이면 반드시 고르세요.
            </p>
          )}
        </div>

        {/* **규격이 치수를 안 주고 비만 주는 일이 흔하다.** 그리고 어겼다고
            막지 않는다 — ISO 6721-4 는 클램프 간 50~100 mm 를 권하는데 어느
            DMA 장비도 그 값을 못 준다. 막으면 실제로 잰 데이터를 못 넣는다. */}
        <div className="space-y-1.5">
          <Label className="text-xs">비율 조건</Label>
          {checks.map((check, index) => (
            <div key={index} className="flex flex-wrap items-center gap-1.5 text-xs">
              <select
                aria-label={`${index + 1}번 조건 분자`}
                className="border-input bg-background h-7 rounded-md border px-1.5 text-xs"
                value={check.numerator}
                onChange={(event) => patchCheck(index, { numerator: event.target.value })}
              >
                <option value="">—</option>
                {numbers.map((field) => (
                  <option key={field.key} value={field.key}>
                    {field.label}
                  </option>
                ))}
              </select>
              <span>/</span>
              <select
                aria-label={`${index + 1}번 조건 분모`}
                className="border-input bg-background h-7 rounded-md border px-1.5 text-xs"
                value={check.denominator}
                onChange={(event) => patchCheck(index, { denominator: event.target.value })}
              >
                <option value="">—</option>
                {numbers.map((field) => (
                  <option key={field.key} value={field.key}>
                    {field.label}
                  </option>
                ))}
              </select>
              <span>=</span>
              <Input
                aria-label={`${index + 1}번 조건 최소`}
                placeholder="최소"
                inputMode="decimal"
                className="h-7 w-16 text-xs"
                value={check.minimum ?? ''}
                onChange={(event) =>
                  patchCheck(index, { minimum: numberOrNull(event.target.value) })
                }
              />
              <span>~</span>
              <Input
                aria-label={`${index + 1}번 조건 최대`}
                placeholder="최대"
                inputMode="decimal"
                className="h-7 w-16 text-xs"
                value={check.maximum ?? ''}
                onChange={(event) =>
                  patchCheck(index, { maximum: numberOrNull(event.target.value) })
                }
              />
              <Input
                aria-label={`${index + 1}번 조건 이유`}
                placeholder="왜 이 조건이 있나 (안 적어도 됩니다)"
                className="h-7 flex-1 text-xs"
                value={check.help ?? ''}
                onChange={(event) => patchCheck(index, { help: event.target.value || null })}
              />
              <Button
                size="icon"
                variant="ghost"
                className="size-7"
                aria-label={`${index + 1}번 조건 빼기`}
                onClick={() => setChecks((now) => now.filter((_, at) => at !== index))}
              >
                <Trash2 className="size-3.5" />
              </Button>
            </div>
          ))}
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              disabled={numbers.length < 2}
              onClick={() =>
                setChecks((now) => [
                  ...now,
                  { numerator: '', denominator: '', minimum: null, maximum: null, help: null },
                ])
              }
            >
              <Plus className="size-3.5" />
              조건 더하기
            </Button>
            <span className="text-muted-foreground text-xs">
              {numbers.length < 2
                ? '치수 칸이 둘 이상이어야 비를 잴 수 있습니다.'
                : '어겨도 저장은 됩니다 — 시편 화면이 붉게 말합니다.'}
            </span>
          </div>
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
