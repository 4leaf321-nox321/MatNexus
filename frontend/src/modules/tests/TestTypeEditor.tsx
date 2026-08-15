/**
 * 시험 종류 정의 편집.
 *
 * **잠근 것은 이유와 함께 잠근다.** 등록된 시험이 있으면 채널의 key·단위·차원을
 * 못 바꾸는데, 그냥 회색으로만 만들면 사람은 고장인 줄 안다. 왜 잠겼는지 옆에
 * 적어 둔다.
 *
 * 잠그는 이유:
 *   key      Parquet 컬럼 이름이자 `Curve.channels` 의 값이다. 바꾸면 저장된
 *            곡선을 못 읽고, 오류가 아니라 조용히 "채널 없음" 이 된다.
 *   si_unit  저장된 숫자는 그대로인데 뜻이 바뀐다 — 3466.4 N 이 3466.4 kN 이
 *            된다. **숫자가 그대로라 화면 어디에도 티가 안 난다.**
 *
 * 라벨·정렬·필수여부는 언제든 바꾼다. 해석을 바꾸지 않기 때문이다.
 */

import { useEffect, useState } from 'react'
import { Lock, Plus, Trash2 } from 'lucide-react'

import { testsApi } from '@/modules/tests/api'
import type { Parser, TestType } from '@/modules/tests/api'
import { DIMENSIONS, SI_BY_DIMENSION, VALUE_TYPES, display } from '@/modules/tests/units'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import { useResource } from '@/shared/hooks/useResource'

interface ChannelRow {
  key: string
  label: string
  dimension: string
  si_unit: string
  is_required: boolean
  /** 이미 저장돼 있던 채널인가. 데이터가 있으면 이런 줄만 잠긴다. */
  existing: boolean
}

interface ConditionRow {
  key: string
  label: string
  value_type: string
  dimension: string | null
  si_unit: string | null
  is_required: boolean
  existing: boolean
}

interface Props {
  /** 없으면 새로 만든다. */
  type: TestType | null
  open: boolean
  onClose: () => void
  onSaved: () => void
}

export function TestTypeEditor({ type, open, onClose, onSaved }: Props) {
  const parsers = useResource(
    () => (open ? testsApi.parsers() : Promise.resolve([])),
    [open]
  )
  const [form, setForm] = useState({
    key: '',
    label: '',
    abbr: '',
    description: '',
    parser_key: '',
    is_active: true,
  })
  const [channels, setChannels] = useState<ChannelRow[]>([])
  const [conditions, setConditions] = useState<ConditionRow[]>([])
  const [error, setError] = useState<Error | null>(null)
  const [saving, setSaving] = useState(false)

  const creating = type === null
  const locked = (type?.run_count ?? 0) > 0

  useEffect(() => {
    if (!open) return
    setError(null)
    setForm({
      key: type?.key ?? '',
      label: type?.label ?? '',
      abbr: type?.abbr ?? '',
      description: type?.description ?? '',
      parser_key: type?.parser_key ?? '',
      is_active: type?.is_active ?? true,
    })
    setChannels(
      (type?.channels ?? []).map((channel) => ({
        key: channel.key,
        label: channel.label,
        dimension: channel.dimension,
        si_unit: channel.si_unit,
        is_required: channel.is_required,
        existing: true,
      }))
    )
    setConditions(
      (type?.conditions ?? []).map((field) => ({
        key: field.key,
        label: field.label,
        value_type: field.value_type,
        dimension: field.dimension,
        si_unit: field.si_unit,
        is_required: field.is_required,
        existing: true,
      }))
    )
  }, [open, type])

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const payload = {
        label: form.label,
        abbr: form.abbr,
        description: form.description || null,
        parser_key: form.parser_key || null,
        is_active: form.is_active,
        sort_order: type?.channels.length ? 0 : 0,
        max_upload_bytes: null,
        channels: channels.map((channel, index) => ({
          key: channel.key,
          label: channel.label,
          dimension: channel.dimension,
          si_unit: channel.si_unit,
          is_required: channel.is_required,
          sort_order: index * 10,
        })),
        conditions: conditions.map((field, index) => ({
          key: field.key,
          label: field.label,
          value_type: field.value_type,
          dimension: field.dimension,
          si_unit: field.si_unit,
          choices: null,
          is_required: field.is_required,
          sort_order: index * 10,
        })),
      }
      if (creating) await testsApi.createType({ ...payload, key: form.key })
      else await testsApi.updateType(form.key, payload)
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{creating ? '시험 종류 만들기' : `${type?.label} 편집`}</DialogTitle>
          <DialogDescription>
            정의는 데이터입니다 — 배포 없이 추가·수정됩니다. 다만 파일을 실제로 읽는
            파서는 코드입니다.
          </DialogDescription>
        </DialogHeader>

        {locked && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
            <p className="flex items-center gap-1.5 font-medium text-amber-700 dark:text-amber-500">
              <Lock className="size-4" />이 종류로 등록된 시험이 {type?.run_count}건 있습니다
            </p>
            <p className="mt-1 text-xs text-amber-800 dark:text-amber-400">
              채널의 <b>키·단위·차원</b>은 바꿀 수 없고 채널을 지울 수도 없습니다. 저장된
              숫자는 그대로인데 뜻만 바뀌어, 화면 어디에도 티가 나지 않는 오류가 되기
              때문입니다. 라벨·필수여부·순서는 언제든 바꿀 수 있습니다.
            </p>
          </div>
        )}

        <ErrorNotice error={parsers.error ?? error} />

        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="key">키</Label>
            <Input
              id="key"
              value={form.key}
              disabled={!creating}
              placeholder="compression"
              onChange={(event) =>
                setForm((current) => ({ ...current, key: event.target.value }))
              }
            />
            <p className="text-muted-foreground text-xs">
              {creating ? '소문자·숫자·밑줄. 나중에 못 바꿉니다.' : '만든 뒤에는 못 바꿉니다.'}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="label">이름</Label>
            <Input
              id="label"
              value={form.label}
              placeholder="압축시험"
              onChange={(event) =>
                setForm((current) => ({ ...current, label: event.target.value }))
              }
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="abbr">약어</Label>
            <Input
              id="abbr"
              value={form.abbr}
              placeholder="COM"
              onChange={(event) =>
                setForm((current) => ({ ...current, abbr: event.target.value }))
              }
            />
            <p className="text-muted-foreground text-xs">시험 이름에 들어갑니다</p>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>파서</Label>
          <Select
            value={form.parser_key || 'none'}
            onValueChange={(value) =>
              setForm((current) => ({ ...current, parser_key: value === 'none' ? '' : value }))
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">없음 — 파일을 읽지 못합니다</SelectItem>
              {(parsers.data ?? []).map((parser: Parser) => (
                <SelectItem key={parser.id} value={parser.id}>
                  {parser.label}
                  <span className="text-muted-foreground ml-2 font-mono text-xs">
                    {parser.extensions.join(' ')}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-muted-foreground text-xs">
            <b>파서는 정의로 만들 수 없습니다 — 코드입니다.</b> 새 장비 형식을 읽으려면
            <code className="mx-1">matcore/parsers</code>에 플러그인을 더해야 합니다.
          </p>
        </div>

        <RowEditor
          title="채널 (곡선의 열)"
          hint="파일에서 읽어 곡선으로 만들 열입니다. 저장은 SI 단위로 합니다."
          rows={channels}
          locked={locked}
          onAdd={() =>
            setChannels((current) => [
              ...current,
              {
                key: '',
                label: '',
                dimension: 'length',
                si_unit: 'm',
                is_required: true,
                existing: false,
              },
            ])
          }
          onRemove={(index) =>
            setChannels((current) => current.filter((_, position) => position !== index))
          }
          onChange={(index, change) =>
            setChannels((current) =>
              current.map((row, position) =>
                position === index ? { ...row, ...change } : row
              )
            )
          }
        />

        <RowEditor
          title="조건 (입력 항목)"
          hint="업로드할 때 사람이 입력합니다. 단위가 있으면 화면이 실무 단위로 받아 서버가 환산합니다."
          rows={conditions}
          locked={locked}
          withValueType
          onAdd={() =>
            setConditions((current) => [
              ...current,
              {
                key: '',
                label: '',
                value_type: 'number',
                dimension: 'temperature',
                si_unit: 'K',
                is_required: false,
                existing: false,
              },
            ])
          }
          onRemove={(index) =>
            setConditions((current) => current.filter((_, position) => position !== index))
          }
          onChange={(index, change) =>
            setConditions((current) =>
              current.map((row, position) =>
                position === index ? { ...row, ...change } : row
              )
            )
          }
        />

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            취소
          </Button>
          <Button
            onClick={save}
            disabled={saving || !form.key || !form.label || !form.abbr || channels.length === 0}
          >
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface RowLike {
  key: string
  label: string
  dimension: string | null
  si_unit: string | null
  is_required: boolean
  value_type?: string
  existing: boolean
}

function RowEditor({
  title,
  hint,
  rows,
  locked,
  withValueType,
  onAdd,
  onRemove,
  onChange,
}: {
  title: string
  hint: string
  rows: RowLike[]
  locked: boolean
  withValueType?: boolean
  onAdd: () => void
  onRemove: (index: number) => void
  onChange: (index: number, change: Record<string, unknown>) => void
}) {
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <div>
          <Label>{title}</Label>
          <p className="text-muted-foreground text-xs">{hint}</p>
        </div>
        <Button size="sm" variant="secondary" onClick={onAdd}>
          <Plus className="size-3.5" />
          추가
        </Button>
      </div>

      {rows.length === 0 && (
        <p className="text-muted-foreground rounded-md border py-3 text-center text-xs">
          없습니다.
        </p>
      )}

      {rows.map((row, index) => {
        // 데이터가 있어도 **새로 더한 줄은 자유롭다** — 기존 데이터의 해석을
        // 바꾸지 않기 때문이다.
        const frozen = locked && row.existing
        return (
          <div key={index} className="flex items-end gap-2 rounded-md border p-2">
            <div className="w-32 space-y-1">
              <Label className="text-muted-foreground text-xs">
                키 {frozen && <Lock className="inline size-3" />}
              </Label>
              <Input
                className="h-8 font-mono text-xs"
                value={row.key}
                disabled={frozen}
                placeholder="force"
                onChange={(event) => onChange(index, { key: event.target.value })}
              />
            </div>
            <div className="flex-1 space-y-1">
              <Label className="text-muted-foreground text-xs">이름</Label>
              <Input
                className="h-8"
                value={row.label}
                placeholder="하중"
                onChange={(event) => onChange(index, { label: event.target.value })}
              />
            </div>

            {withValueType && (
              <div className="w-24 space-y-1">
                <Label className="text-muted-foreground text-xs">종류</Label>
                <Select
                  value={row.value_type ?? 'number'}
                  onValueChange={(value) => onChange(index, { value_type: value })}
                >
                  <SelectTrigger className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {VALUE_TYPES.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="w-32 space-y-1">
              <Label className="text-muted-foreground text-xs">
                차원 {frozen && <Lock className="inline size-3" />}
              </Label>
              <Select
                value={row.dimension ?? 'length'}
                disabled={frozen}
                onValueChange={(value) =>
                  // 차원이 정해지면 저장 단위도 정해진다 — 따로 고를 것이 없다.
                  onChange(index, {
                    dimension: value,
                    si_unit: SI_BY_DIMENSION[value] ?? '1',
                  })
                }
              >
                <SelectTrigger className="h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DIMENSIONS.map((dimension) => (
                    <SelectItem key={dimension} value={dimension}>
                      {dimension}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* 저장 단위는 **고르는 것이 아니다.** 값은 언제나 그 차원의 정본 SI 로
                저장된다. 고를 수 있게 두면 정의에 `MPa` 라고 적었는데 저장된 숫자는
                Pa 인 상태가 만들어지고, 화면·계산이 10⁶ 배 틀린다 — 숫자가 멀쩡해
                보여 티가 나지 않는다. 서버도 이것을 거절한다.
                사람이 보는 단위는 아래 '표시' 열이 따로 정한다. */}
            <div className="w-24 space-y-1">
              <Label className="text-muted-foreground text-xs">저장 단위</Label>
              <div className="bg-muted flex h-8 items-center rounded-md px-2 font-mono text-xs">
                {SI_BY_DIMENSION[row.dimension ?? ''] ?? '1'}
              </div>
            </div>

            <div className="w-20 space-y-1">
              <Label className="text-muted-foreground text-xs">표시</Label>
              <div className="flex h-8 items-center px-2 font-mono text-xs">
                {display(row.si_unit, row.dimension).unit || '—'}
              </div>
            </div>

            <label className="flex h-8 items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={row.is_required}
                onChange={(event) => onChange(index, { is_required: event.target.checked })}
              />
              필수
            </label>

            <Button
              size="sm"
              variant="ghost"
              disabled={frozen}
              title={frozen ? '등록된 시험이 있어 지울 수 없습니다' : '지우기'}
              onClick={() => onRemove(index)}
            >
              <Trash2 className="size-3.5" />
            </Button>
            {!row.existing && <Badge variant="outline">새로</Badge>}
          </div>
        )
      })}
    </section>
  )
}
