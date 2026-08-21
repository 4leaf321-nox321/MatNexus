/**
 * 치수 칸 정의 — **규격이 어떤 치수를 갖는지 여기서 정한다.**
 *
 * ## 어디에 사는 값인가
 *
 * 칸은 **시험 종류의 것**이다(`test_specimen_fields`). 인장 규격 전부가 같은
 * 칸을 쓰고, DMA 규격 전부가 다른 칸을 쓴다 — 규격마다 따로 두면 `ASTM E8` 과
 * `JIS 5호` 의 '게이지 길이' 가 서로 다른 이름이 되고, 그러면 시편 치수를
 * 물려받는 쪽이 규격마다 다른 키를 알아야 한다.
 *
 * ## 그런데 왜 기준정보 화면에서 고치는가
 *
 * **고치고 싶어지는 자리가 여기**이기 때문이다. "ASTM E8 에 그립부 길이도 적고
 * 싶은데 칸이 없네" 는 규격을 적다가 나오는 말이지 시험 종류 관리 화면에서
 * 나오는 말이 아니다. 두 화면을 오가게 하면 대개 그냥 포기한다.
 *
 * ## 키는 계약이다
 *
 * 이미 저장된 규격의 치수가 이 키로 들어 있다. 키를 바꾸면 그 값들이 갈 곳을
 * 잃는다 — 그래서 **만든 뒤에는 못 고친다.** 이름은 얼마든지 고쳐도 된다
 * (`TestType.key`/`label` 을 나눈 것과 같은 관계다).
 */

import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

import { vocabularyApi } from '@/modules/vocabulary/api'
import type { SpecimenFieldSave, TermKind } from '@/modules/vocabulary/api'
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
import { useResource } from '@/shared/hooks/useResource'

interface Row extends SpecimenFieldSave {
  /** 이미 저장된 칸인가. **저장된 키는 못 고친다** — 계약이라서. */
  saved: boolean
}

/** 사람이 친 이름에서 키를 만든다. 영문·숫자·밑줄만 남긴다. */
function keyFrom(label: string): string {
  const cleaned = label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  // 서버가 `^[a-z][a-z0-9_]*$` 를 요구한다. 한글만 친 경우 빈 문자열이 되므로
  // 사람이 직접 키를 채우게 둔다 — 지어내면 `field_1` 같은 것이 쌓인다.
  return /^[a-z]/.test(cleaned) ? cleaned : ''
}

export function SpecimenFieldsDialog({
  slug,
  kind,
  kindLabel,
  onClose,
  onSaved,
}: {
  slug: string
  kind: string
  kindLabel: string
  onClose: () => void
  onSaved: () => void
}) {
  const loaded = useResource(() => vocabularyApi.specimenFields(slug, kind), [slug, kind])
  const [rows, setRows] = useState<Row[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    setRows(
      (loaded.data ?? []).map((field) => ({
        key: field.key,
        label: field.label,
        dimension: field.dimension,
        si_unit: field.si_unit,
        is_required: field.is_required,
        help: field.help ?? null,
        saved: true,
      }))
    )
  }, [loaded.data])

  function patch(index: number, change: Partial<Row>) {
    setRows((current) =>
      current.map((row, at) => (at === index ? { ...row, ...change } : row))
    )
  }

  async function save() {
    setBusy(true)
    setError(null)
    try {
      await vocabularyApi.saveSpecimenFields(
        slug,
        kind,
        rows.map(({ saved: _saved, ...field }) => field)
      )
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const dropped = (loaded.data ?? []).filter(
    (field) => !rows.some((row) => row.key === field.key)
  )

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{kindLabel} — 치수 칸</DialogTitle>
          <DialogDescription>
            이 종류의 <b>모든 규격</b>이 이 칸을 씁니다. 규격마다 다른 칸을 두면 같은
            게이지 길이가 규격마다 다른 이름이 되고, 시편이 물려받을 방법이 없어집니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={loaded.error ?? error} />

        <div className="space-y-1.5">
          {rows.map((row, index) => (
            <div key={index} className="grid grid-cols-[1fr_9rem_5rem_auto] items-start gap-2">
              <div>
                <Input
                  aria-label={`${index + 1}번 칸 이름`}
                  placeholder="이름 (게이지 길이)"
                  className="h-8"
                  value={row.label}
                  onChange={(event) => {
                    const label = event.target.value
                    // 새 칸은 이름에서 키를 만들어 준다. 저장된 칸은 안 건드린다.
                    patch(index, row.saved ? { label } : { label, key: keyFrom(label) })
                  }}
                />
                <Input
                  aria-label={`${index + 1}번 칸 설명`}
                  placeholder="설명 (안 적어도 됩니다)"
                  className="mt-1 h-7 text-xs"
                  value={row.help ?? ''}
                  onChange={(event) => patch(index, { help: event.target.value || null })}
                />
              </div>
              <div>
                <Input
                  aria-label={`${index + 1}번 칸 키`}
                  placeholder="gauge_length"
                  className="h-8 font-mono text-xs"
                  value={row.key}
                  disabled={row.saved}
                  onChange={(event) => patch(index, { key: event.target.value })}
                />
                {row.saved && (
                  /* **키는 계약이다.** 이미 저장된 규격의 치수가 이 키로 들어
                     있어서, 바꾸면 그 값들이 갈 곳을 잃는다. */
                  <p className="text-muted-foreground mt-0.5 text-xs">쓰이는 중 · 고정</p>
                )}
              </div>
              <label className="flex items-center gap-1 pt-2 text-xs">
                <input
                  type="checkbox"
                  aria-label={`${index + 1}번 칸 필수`}
                  checked={row.is_required}
                  onChange={(event) => patch(index, { is_required: event.target.checked })}
                />
                필수
              </label>
              <Button
                size="icon"
                variant="ghost"
                className="size-8"
                aria-label={`${index + 1}번 칸 빼기`}
                onClick={() => setRows((current) => current.filter((_, at) => at !== index))}
              >
                <Trash2 className="size-3.5" />
              </Button>
            </div>
          ))}

          <Button
            size="sm"
            variant="outline"
            className="h-8 text-xs"
            onClick={() =>
              setRows((current) => [
                ...current,
                {
                  key: '',
                  label: '',
                  dimension: 'length',
                  si_unit: 'm',
                  is_required: false,
                  help: null,
                  saved: false,
                },
              ])
            }
          >
            <Plus className="size-3.5" />
            칸 더하기
          </Button>
        </div>

        {/* **뺀 칸의 값은 안 지운다.** 화면에서 사라질 뿐이고, 되살리면 다시
            보인다 — 지워 버리면 되살릴 방법이 없다. */}
        {dropped.length > 0 && (
          <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2.5 text-xs">
            <b>{dropped.map((field) => field.label).join(', ')}</b> 을(를) 뺍니다. 이미 그
            치수를 적어 둔 규격에서는 <b>화면에 안 보이게 됩니다</b> — 값 자체는 남아
            있어서, 칸을 되살리면 다시 나옵니다.
          </p>
        )}

        <p className="text-muted-foreground text-xs">
          길이만 다룹니다(저장 m, 화면 mm). 다른 차원이 필요해지면 그때 늘립니다.
        </p>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
          <Button
            onClick={() => void save()}
            disabled={busy || rows.some((row) => !row.key || !row.label)}
          >
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** 종류를 먼저 고르게 하는 얇은 껍데기. 축에서 바로 열 때 쓴다. */
export function SpecimenFieldsPicker({
  slug,
  onClose,
}: {
  slug: string
  onClose: () => void
}) {
  const kinds = useResource(() => vocabularyApi.kinds(slug), [slug])
  const [picked, setPicked] = useState<TermKind | null>(null)

  if (picked) {
    return (
      <SpecimenFieldsDialog
        slug={slug}
        kind={picked.key}
        kindLabel={picked.label}
        onClose={onClose}
        onSaved={onClose}
      />
    )
  }

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>치수 칸 정의</DialogTitle>
          <DialogDescription>
            어느 시험의 규격을 고칠까요? <b>칸은 시험 종류마다 다릅니다</b> — 인장 규격에는
            어깨 반경이 있고 DMA 규격에는 지지 간격이 있습니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={kinds.error} />

        <div className="space-y-1.5">
          <Label className="text-xs">시험 종류</Label>
          <div className="flex flex-wrap gap-1.5">
            {(kinds.data ?? []).map((item) => (
              <Button
                key={item.key}
                size="sm"
                variant="outline"
                className="h-8 text-xs"
                onClick={() => setPicked(item)}
              >
                {item.label}
              </Button>
            ))}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
