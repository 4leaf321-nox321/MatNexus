/**
 * 시편 치수 고치기.
 *
 * **넣을 자리가 없었다.** '시편 추가' 와 '시험 등록' 에서는 치수를 넣을 수
 * 있는데, 만들고 난 뒤에는 고칠 길이 없었다. 일괄 등록은 시편을 방향만 주고
 * 만들므로 **치수가 빈 시편이 무더기로 생긴다** — 그 상태로는 처리가 첫 단계
 * (하중÷단면적)에서 막힌다.
 *
 * ## 칸을 화면에 박지 않는다
 *
 * 전에는 두께·폭·게이지 세 칸이 여기 적혀 있었다. 그래서 **환봉 시편은 직경을
 * 적을 자리가 아예 없었다** — `specimens` 테이블에도 직경 컬럼이 없었다. 같은
 * 인장 시험인데 평판은 폭·두께를 갖고 환봉은 직경을 갖는다.
 *
 * 이제 **규격이 칸을 정한다**(ADR 0010). 이 화면은 규격이 준 칸을 그린다 —
 * 환봉 규격을 고르면 직경 칸이 나온다.
 *
 * ## 규격값은 흐리게, 잰 값은 진하게
 *
 * 빈 칸의 흐린 숫자가 규격의 공칭이다. 그대로 두면 그 값이 쓰이고, 재서 넣으면
 * 그 값이 이긴다. **합쳐서 하나로 보여 주면 사람은 전부 실측으로 읽는다.**
 *
 * 방향과 번호는 여기서 안 바꾼다. 그 둘이 시편 이름을 만들고, 이름은 시험까지
 * 따라 내려간다(ADR 0004). 잘못 만들었으면 지우고 다시 만드는 편이 낫다 —
 * 시험이 달린 시편은 서버가 삭제를 막는다.
 *
 * 장비 파일이 치수를 갖고 있으면 손으로 넣지 않아도 된다. 시험 상세의 '처리'
 * 탭이나 일괄 등록 화면에서 **파일 값으로 채우기**를 쓰는 쪽이 빠르고 정확하다.
 */

import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { materialsApi } from '@/modules/materials/api'
import { VocabularyField } from '@/modules/vocabulary/VocabularyField'
import type { Specimen, SpecimenSize, SpecimenSizes } from '@/modules/materials/api'
import { ApiError } from '@/shared/api/client'
import { Badge } from '@/shared/components/ui/badge'
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

interface Props {
  specimen: Specimen
  open: boolean
  onClose: () => void
  onSaved: () => void
}

/** SI 숫자를 화면 단위 문자열로. 빈 값은 빈 칸이다 — 0 이 아니다. */
function shownValue(value: number | null | undefined, field: SpecimenSize): string {
  if (value == null) return ''
  return String(Number(toDisplay(value, field.si_unit, field.dimension).toPrecision(10)))
}

export function EditSpecimenDialog({ specimen, open, onClose, onSaved }: Props) {
  const [standard, setStandard] = useState(specimen.standard ?? '')
  const [note, setNote] = useState(specimen.note ?? '')
  const [sizes, setSizes] = useState<SpecimenSizes | null>(null)
  /** 잰 값만 들고 있다. 문자열인 이유는 `Number('0.')` 이 소수점을 지우기 때문. */
  const [measured, setMeasured] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setStandard(specimen.standard ?? '')
    setNote(specimen.note ?? '')
    setFailure(null)
    let alive = true
    materialsApi
      .dimensions(specimen.id)
      .then((loaded) => {
        if (!alive) return
        setSizes(loaded)
        setMeasured(
          Object.fromEntries(
            loaded.fields.map((field) => [field.key, shownValue(field.measured, field)])
          )
        )
      })
      .catch((error: unknown) => {
        if (alive) setFailure(error instanceof ApiError ? error.message : '치수를 읽지 못했습니다.')
      })
    return () => {
      alive = false
    }
  }, [open, specimen])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setFailure(null)
    try {
      // **규격을 먼저 저장한다.** 칸을 정하는 쪽이 규격이라 순서가 있다 —
      // 새 규격의 칸은 다음 열 때 나온다.
      await materialsApi.updateSpecimen(specimen.id, {
        standard: standard === '' ? null : standard,
        note: note === '' ? null : note,
      })

      const values: Record<string, number> = {}
      for (const field of sizes?.fields ?? []) {
        const text = (measured[field.key] ?? '').trim()
        if (text === '') continue // 빈 칸은 "안 쟀다" — 규격의 공칭이 쓰인다
        const value = fromDisplay(Number(text), field.si_unit, field.dimension)
        if (Number.isFinite(value)) values[field.key] = value
      }
      await materialsApi.saveDimensions(specimen.id, values)
      onSaved()
    } catch (error) {
      setFailure(error instanceof ApiError ? error.message : '저장하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  const fields = sizes?.fields ?? []
  const changedStandard = sizes !== null && standard !== (specimen.standard ?? '')

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            시편 수정
            <Badge variant="secondary">{specimen.orientation}</Badge>
          </DialogTitle>
          <DialogDescription className="font-mono text-xs">
            {specimen.record_name}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-3">
          <VocabularyField
            slug="specimen_standard"
            label="시편 규격"
            value={standard}
            onChange={setStandard}
          />

          {/* **규격이 칸을 정한다.** 바꾸면 칸도 바뀌는데, 그건 저장한 뒤라야
              안다 — 미리 그리면 아직 저장 안 된 규격의 칸을 채우게 된다. */}
          {changedStandard && (
            <p className="text-muted-foreground text-xs">
              규격을 바꿨습니다. <b>저장하면 치수 칸이 새 규격의 것으로 바뀝니다.</b>
            </p>
          )}

          {fields.length === 0 ? (
            <p className="text-muted-foreground rounded-md border p-3 text-xs">
              이 시편에는 치수 칸이 없습니다. <b>규격이 칸을 정합니다</b> — 규격을 고르거나,
              기준정보 &gt; 시편 규격에서 그 규격의 치수 칸을 먼저 만드세요.
            </p>
          ) : (
            <div className="space-y-2">
              {fields.map((field) => {
                const unit = display(field.si_unit, field.dimension).unit
                return (
                  <div key={field.key} className="grid grid-cols-[9rem_1fr] items-start gap-2">
                    <Label htmlFor={`sp-${field.key}`} className="pt-1.5 text-xs">
                      {field.label}
                      {unit && <span className="text-muted-foreground ml-1">({unit})</span>}
                    </Label>
                    <div>
                      <Input
                        id={`sp-${field.key}`}
                        inputMode="decimal"
                        className="h-8"
                        // 흐린 숫자가 규격의 공칭이다. 비워 두면 그 값이 쓰인다.
                        placeholder={
                          field.nominal == null ? '' : `규격 ${shownValue(field.nominal, field)}`
                        }
                        value={measured[field.key] ?? ''}
                        onChange={(event) =>
                          setMeasured((current) => ({
                            ...current,
                            [field.key]: event.target.value,
                          }))
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

          {/* **어긴 채로 쟀다는 것이 보여야 한다.** 막지는 않는다 — 규격이
              권장값을 주는데 장비가 못 맞추는 일이 실제로 있다(ISO 6721-4 는
              클램프 간 50~100 mm 를 권하는데 어느 DMA 장비도 그 값을 못 준다).
              막으면 실제로 잰 데이터를 못 넣고, 사람은 시스템 밖에서 일한다. */}
          {(sizes?.warnings ?? []).length > 0 && (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2.5 text-xs">
              <b>규격이 요구하는 비율을 벗어났습니다.</b> 저장은 됩니다 — 다만 이 조건을
              어긴 채로 쟀다는 것을 시험 보고서에 함께 적어야 재현이 됩니다.
              {(sizes?.warnings ?? []).map((warning, index) => (
                <p key={index} className="mt-1">
                  {warning.condition} — 지금 <b>{warning.actual.toPrecision(3)}</b>
                  {warning.help && <span className="text-muted-foreground"> · {warning.help}</span>}
                </p>
              ))}
            </div>
          )}

          {/* **단면적이 왜 안 나오는지 여기서 말한다.** 처리 화면에서 만나면
              사람은 어디를 채워야 하는지 모른 채 되돌아온다. */}
          {sizes && (
            <p
              className={
                sizes.area == null ? 'text-destructive text-xs' : 'text-muted-foreground text-xs'
              }
            >
              {sizes.area == null ? (
                (sizes.area_problem ?? '단면적을 낼 수 없습니다.')
              ) : (
                <>
                  단면적 <b>{(sizes.area * 1e6).toPrecision(4)} mm²</b>
                  {sizes.cross_section_label && ` · ${sizes.cross_section_label}`} — 하중을 이 값으로
                  나눠 응력을 만듭니다.
                </>
              )}
            </p>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="sp-note">메모</Label>
            <Input
              id="sp-note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>

          {failure && <p className="text-destructive text-sm">{failure}</p>}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>
              취소
            </Button>
            <Button type="submit" disabled={busy}>
              저장
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
