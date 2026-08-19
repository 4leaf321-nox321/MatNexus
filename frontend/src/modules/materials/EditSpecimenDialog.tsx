/**
 * 시편 치수 고치기.
 *
 * **넣을 자리가 없었다.** '시편 추가' 와 '시험 등록' 에서는 치수를 넣을 수
 * 있는데, 만들고 난 뒤에는 고칠 길이 없었다. 일괄 등록은 시편을 방향만 주고
 * 만들므로 **치수가 빈 시편이 무더기로 생긴다** — 그 상태로는 처리가 첫 단계
 * (하중÷단면적)에서 막힌다.
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

import { LENGTH_UNIT, materialsApi } from '@/modules/materials/api'
import type { Specimen } from '@/modules/materials/api'
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

interface Props {
  specimen: Specimen
  open: boolean
  onClose: () => void
  onSaved: () => void
}

/** 숫자를 문자열로 들고 있는다 — `Number('0.')` 이 0 이 되어 소수점이 지워진다. */
function initial(specimen: Specimen) {
  return {
    standard: specimen.standard ?? '',
    thickness: specimen.thickness == null ? '' : String(specimen.thickness),
    width: specimen.width == null ? '' : String(specimen.width),
    gauge_length: specimen.gauge_length == null ? '' : String(specimen.gauge_length),
    note: specimen.note ?? '',
  }
}

export function EditSpecimenDialog({ specimen, open, onClose, onSaved }: Props) {
  const [form, setForm] = useState(() => initial(specimen))
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setForm(initial(specimen))
      setFailure(null)
    }
  }, [open, specimen])

  const field = (key: keyof ReturnType<typeof initial>) => ({
    value: form[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value })),
  })

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setFailure(null)
    try {
      await materialsApi.updateSpecimen(specimen.id, {
        standard: form.standard === '' ? null : form.standard,
        // 빈 칸은 보내지 않는다 — 서버가 `exclude_unset` 으로 안 건드린다.
        // 0 을 보내면 "쟀는데 0" 이 되고, 그것은 없는 것과 다르다.
        ...(form.thickness === '' ? {} : { thickness: Number(form.thickness) }),
        ...(form.width === '' ? {} : { width: Number(form.width) }),
        ...(form.gauge_length === '' ? {} : { gauge_length: Number(form.gauge_length) }),
        length_unit: LENGTH_UNIT,
        note: form.note === '' ? null : form.note,
      })
      onSaved()
    } catch (error) {
      setFailure(error instanceof ApiError ? error.message : '저장하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
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
          <div className="space-y-1.5">
            <Label htmlFor="sp-standard">시편 규격</Label>
            <Input
              id="sp-standard"
              placeholder="ASTM E8 subsize / JIS 5호 …"
              {...field('standard')}
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="sp-thickness">두께 (mm)</Label>
              <Input id="sp-thickness" inputMode="decimal" {...field('thickness')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sp-width">폭 (mm)</Label>
              <Input id="sp-width" inputMode="decimal" {...field('width')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sp-gauge">게이지 길이 (mm)</Label>
              <Input id="sp-gauge" inputMode="decimal" {...field('gauge_length')} />
            </div>
          </div>

          {/* **왜 중요한지 적는다.** 빈 칸이면 처리가 첫 단계에서 막히는데,
              그때 나오는 오류만 보고는 여기로 오지 못한다. */}
          <p className="text-muted-foreground text-xs">
            두께와 폭으로 단면적을 구해 <b>하중을 응력으로</b> 바꿉니다. 게이지 길이로는
            변위를 변형률로 바꿉니다 — 비어 있으면 처리가 첫 단계에서 멈춥니다.
          </p>

          <div className="space-y-1.5">
            <Label htmlFor="sp-note">메모</Label>
            <Input id="sp-note" {...field('note')} />
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
