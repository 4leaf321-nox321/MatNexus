/**
 * 시험 원본 업로드.
 *
 * **조건 입력 폼을 정의에서 그린다.** 항목을 화면에 하드코딩하면 시험 종류를
 * 데이터로 둔 이유가 사라진다 — 관리자가 조건을 하나 추가했을 때 배포 없이
 * 화면에 나타나야 한다(수준 2).
 *
 * 업로드는 202 로 끝난다. 파싱은 워커가 하므로 여기서는 "큐에 넣었다" 까지만
 * 알리고, 목록이 스스로 상태를 따라간다.
 */

import { useEffect, useState } from 'react'
import { Loader2, Upload } from 'lucide-react'

import { SpecimenPicker } from '@/modules/materials/SpecimenPicker'
import { LENGTH_UNIT, materialsApi } from '@/modules/materials/api'
import type { Specimen } from '@/modules/materials/api'
import { testsApi } from '@/modules/tests/api'
import { VocabularyField } from '@/modules/vocabulary/VocabularyField'
import type { TestRun, TestType } from '@/modules/tests/api'
import { conditionUnits, display } from '@/shared/units'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { FileDrop } from '@/shared/components/FileDrop'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import { useResource } from '@/shared/hooks/useResource'

interface Props {
  /** 정해져 있으면 고르는 단계를 건너뛴다(시편 줄에서 열 때). 없으면 직접 고른다. */
  specimenId?: string
  specimenName?: string
  /** 시료가 정해진 채로 열 때(측정 의뢰 항목에서) — 그 시료의 시편 중에서 고르거나 하나 만든다. */
  sampleId?: string
  /** 시험 종류를 미리 고른 채로(의뢰 항목의 종류). */
  presetTestType?: string
  /** 조건을 미리 채운 채로 — **표시 단위 값**. 의뢰 항목이 적은 조건이 그대로 온다. */
  presetConditions?: Record<string, string>
  open: boolean
  onClose: () => void
  onDone: () => void
  /** 등록된 시험을 돌려준다 — 의뢰 항목이 그 자리에서 붙인다. */
  onUploaded?: (run: TestRun) => void
}

export function UploadDialog({
  specimenId,
  specimenName,
  sampleId,
  presetTestType,
  presetConditions,
  open,
  onClose,
  onDone,
  onUploaded,
}: Props) {
  const types = useResource(() => (open ? testsApi.types() : Promise.resolve([])), [open])
  const [typeKey, setTypeKey] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [conditions, setConditions] = useState<Record<string, string>>({})
  const [operator, setOperator] = useState('')
  const [instrument, setInstrument] = useState('')
  const [division, setDivision] = useState('')
  const [error, setError] = useState<Error | null>(null)
  const [saving, setSaving] = useState(false)
  const [picked, setPicked] = useState<Specimen | null>(null)
  // 시료가 정해진 채로 열렸을 때 — 그 시료의 시편 목록과 「새 시편」.
  const sampleSpecimens = useResource(
    () => (open && sampleId ? materialsApi.specimens(sampleId) : Promise.resolve([])),
    [open, sampleId]
  )
  const [newOrientation, setNewOrientation] = useState('MD')
  const [making, setMaking] = useState(false)

  const targetId = specimenId ?? picked?.id ?? null
  const targetName = specimenName ?? picked?.record_name

  const available = types.data ?? []
  const selected: TestType | undefined =
    available.find((t) => t.key === typeKey) ?? available[0]

  useEffect(() => {
    if (open) {
      setFile(null)
      setConditions(presetConditions ?? {})
      setOperator('')
      setError(null)
      setPicked(null)
      if (presetTestType) setTypeKey(presetTestType)
    }
  }, [open, presetTestType, presetConditions])

  useEffect(() => {
    if (selected && !typeKey) setTypeKey(selected.key)
  }, [selected, typeKey])

  async function makeSpecimen() {
    if (!sampleId) return
    setMaking(true)
    setError(null)
    try {
      // 치수는 비운다 — 두께·폭은 시편 줄에서 나중에 적는다(측정값이 있어야 응력이 나오지만,
      // 등록을 막을 일은 아니다). 단위 칸은 서버 규약(mm)을 그대로.
      const made = await materialsApi.createSpecimen(sampleId, {
        orientation: newOrientation,
        length_unit: LENGTH_UNIT,
      })
      await sampleSpecimens.reload()
      setPicked(made)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('시편을 만들지 못했습니다.'))
    } finally {
      setMaking(false)
    }
  }

  async function submit() {
    if (!file || !selected || !targetId) return
    setSaving(true)
    setError(null)
    try {
      // 빈 칸은 보내지 않는다 — 서버가 필수 여부를 정의로 판단한다.
      const filled = Object.fromEntries(
        Object.entries(conditions)
          .filter(([, value]) => value !== '')
          .map(([key, value]) => {
            const field = selected.conditions.find((c) => c.key === key)
            return [key, field?.value_type === 'number' ? Number(value) : value]
          })
      )
      const run = await testsApi.upload({
        specimenId: targetId,
        testType: selected.key,
        file,
        conditions: filled,
        conditionUnits: conditionUnits(selected.conditions),
        operator: operator || undefined,
        instrument: instrument || undefined,
        division: division || undefined,
      })
      onUploaded?.(run)
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('업로드에 실패했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  const limitMb = selected ? Math.round(selected.max_upload_bytes_effective / (1024 * 1024)) : 0

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>시험 등록</DialogTitle>
          <DialogDescription>
            {targetName ? `${targetName} 시편에 ` : ''}장비 원본을 올리면 서버가 읽어
            곡선으로 만듭니다. 원본은 그대로 보관됩니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={types.error} />

        {!specimenId && sampleId && (
          <div className="space-y-1.5">
            <Label htmlFor="upload-specimen">시편 (이 의뢰의 시료)</Label>
            {/* **시료는 의뢰가 정했다.** 다른 시료의 시편을 고르게 두면 의뢰가 재지도 않은
                것을 잰 것으로 적는다 — 그 시료의 시편 중에서 고르거나, 없으면 하나 만든다. */}
            <div className="flex flex-wrap items-center gap-2">
              <select
                id="upload-specimen"
                className="border-input bg-background h-9 flex-1 rounded-md border px-2 text-sm"
                value={picked?.id ?? ''}
                onChange={(event) =>
                  setPicked(
                    (sampleSpecimens.data ?? []).find((one) => one.id === event.target.value) ??
                      null
                  )
                }
              >
                <option value="">
                  {(sampleSpecimens.data ?? []).length > 0
                    ? '— 시편을 고르세요 —'
                    : '시편이 없습니다 — 아래에서 만드세요'}
                </option>
                {(sampleSpecimens.data ?? []).map((one) => (
                  <option key={one.id} value={one.id}>
                    {one.record_name}
                  </option>
                ))}
              </select>
              <Input
                className="h-9 w-20 font-mono"
                aria-label="새 시편 방향"
                value={newOrientation}
                onChange={(event) => setNewOrientation(event.target.value.toUpperCase())}
              />
              <Button size="sm" variant="outline" disabled={making} onClick={() => void makeSpecimen()}>
                {making ? <Loader2 className="size-3.5 animate-spin" /> : null}새 시편
              </Button>
            </div>
          </div>
        )}
        {!specimenId && !sampleId && (
          <div className="space-y-1.5">
            <Label>시편</Label>
            <SpecimenPicker onChange={setPicked} />
            {picked && (
              <p className="text-muted-foreground font-mono text-xs">{picked.record_name}</p>
            )}
          </div>
        )}

        {available.length > 1 && (
          <div className="space-y-1.5">
            {/* 버튼을 나열하지 않는다 — 종류가 스무 개로 늘면 그 줄이 화면을 덮는다. */}
            <Label>시험 종류</Label>
            <Select value={selected?.key ?? ''} onValueChange={setTypeKey}>
              <SelectTrigger>
                <SelectValue placeholder="고르세요" />
              </SelectTrigger>
              <SelectContent>
                {available.map((type) => (
                  <SelectItem key={type.key} value={type.key}>
                    {type.label}
                    {type.extensions.length > 0 && (
                      <span className="text-muted-foreground ml-2 font-mono text-xs">
                        {type.extensions.join(' ')}
                      </span>
                    )}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div className="space-y-1.5">
          <Label htmlFor="file">
            원본 파일 {selected?.parser_key && `(${selected.parser_key})`}
          </Label>
          {/* **끌어다 놓기가 일괄 등록에만 있었다.** 같은 일을 하는 두 화면이
              다르게 동작하면, 몸에 밴 동작이 여기서는 아무 일도 안 일어나고
              사람은 그것을 고장으로 읽는다. */}
          <FileDrop
            onFiles={(files) => setFile(files[0] ?? null)}
            hint={`최대 ${limitMb}MB`}
          />
          {file && (
            <p className="text-muted-foreground text-xs">
              고른 파일: <b className="text-foreground font-mono">{file.name}</b>
            </p>
          )}
        </div>

        {selected && selected.conditions.length > 0 && (
          <div className="space-y-1.5">
            <Label>시험 조건</Label>
            <div className="grid grid-cols-2 gap-3">
              {selected.conditions.map((field) => (
                <div key={field.key} className="space-y-1">
                  <Label htmlFor={field.key} className="text-muted-foreground text-xs">
                    {field.label}
                    {field.si_unit && ` (${display(field.si_unit, field.dimension).unit})`}
                    {field.is_required && <span className="text-destructive"> *</span>}
                  </Label>
                  <Input
                    id={field.key}
                    type={field.value_type === 'number' ? 'number' : 'text'}
                    step="any"
                    value={conditions[field.key] ?? ''}
                    onChange={(event) =>
                      setConditions((current) => ({
                        ...current,
                        [field.key]: event.target.value,
                      }))
                    }
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-1.5">
          <Label htmlFor="operator">시험자 (선택)</Label>
          <Input
            id="operator"
            value={operator}
            onChange={(event) => setOperator(event.target.value)}
          />
        </div>

        {/* **장비는 기준정보다**(ADR 0010). 'Zwick Z100' 과 'zwick z100' 이 갈리면
            장비별 비교가 무의미해진다. 시험자는 기준정보가 아니다 — 시험을 돌린
            사람이 시스템 계정이 없을 수 있고, 집계 축으로 쓸 계획도 없다. */}
        <VocabularyField
          slug="instrument"
          label="장비 (선택)"
          value={instrument}
          onChange={setInstrument}
        />

        {/* **사업부는 부서와 다르다.** 부서는 누가 볼 수 있는가를 정하고,
            사업부는 누가 낸 데이터인가를 적는다 — 한 부서 계정으로 여러
            사업부의 판을 올리는 일이 있고, 그때 부서로는 둘을 못 가른다. */}
        <VocabularyField
          slug="division"
          label="사업부 (선택)"
          value={division}
          onChange={setDivision}
        />

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            취소
          </Button>
          {/* **도는 동안 도는 것이 보여야 한다.** 파일을 올리고 읽는 데 몇 초가
              걸리는데 단추 글자만 바뀌면 「눌렸나」 를 확신 못 해 다시 누른다. */}
          <Button onClick={submit} disabled={saving || !file || !selected || !targetId}>
            {saving ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Upload className="size-4" />
            )}
            {/* 「읽는 중」 이라고 안 적는다 — 읽기는 올린 뒤 서버가 이어서
                하고, 그 진행은 목록의 상태 열이 보여 준다. 여기서 읽는다고 하면
                창이 닫힌 뒤 「읽는 중」 인 줄을 보고 고장으로 여긴다. */}
            {saving ? '올리는 중…' : '업로드'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
