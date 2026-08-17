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
import { Upload } from 'lucide-react'

import { SpecimenPicker } from '@/modules/materials/SpecimenPicker'
import type { Specimen } from '@/modules/materials/api'
import { testsApi } from '@/modules/tests/api'
import type { TestType } from '@/modules/tests/api'
import { conditionUnits, display } from '@/shared/units'
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
  open: boolean
  onClose: () => void
  onDone: () => void
}

export function UploadDialog({ specimenId, specimenName, open, onClose, onDone }: Props) {
  const types = useResource(() => (open ? testsApi.types() : Promise.resolve([])), [open])
  const [typeKey, setTypeKey] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [conditions, setConditions] = useState<Record<string, string>>({})
  const [operator, setOperator] = useState('')
  const [error, setError] = useState<Error | null>(null)
  const [saving, setSaving] = useState(false)
  const [picked, setPicked] = useState<Specimen | null>(null)

  const targetId = specimenId ?? picked?.id ?? null
  const targetName = specimenName ?? picked?.record_name

  const available = types.data ?? []
  const selected: TestType | undefined =
    available.find((t) => t.key === typeKey) ?? available[0]

  useEffect(() => {
    if (open) {
      setFile(null)
      setConditions({})
      setOperator('')
      setError(null)
      setPicked(null)
    }
  }, [open])

  useEffect(() => {
    if (selected && !typeKey) setTypeKey(selected.key)
  }, [selected, typeKey])

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
      await testsApi.upload({
        specimenId: targetId,
        testType: selected.key,
        file,
        conditions: filled,
        conditionUnits: conditionUnits(selected.conditions),
        operator: operator || undefined,
      })
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('업로드에 실패했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  const limitMb = selected ? Math.round(selected.max_upload_bytes / (1024 * 1024)) : 0

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>시험 등록</DialogTitle>
          <DialogDescription>
            {targetName ? `${targetName} 시편에 ` : ''}장비 원본을 올리면 서버가 읽어
            곡선으로 만듭니다. 원본은 그대로 보관됩니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={types.error} />

        {!specimenId && (
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
          <Input
            id="file"
            type="file"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <p className="text-muted-foreground text-xs">최대 {limitMb}MB</p>
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

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            취소
          </Button>
          <Button onClick={submit} disabled={saving || !file || !selected || !targetId}>
            <Upload className="size-4" />
            {saving ? '올리는 중…' : '올리기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
