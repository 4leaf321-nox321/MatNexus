/**
 * 치수 칸 정의 — **분류의 기본 칸이냐, 이 값만의 칸이냐.**
 *
 * 같은 창이 두 자리에서 쓰인다.
 *
 *   시편 분류의 값에서   그 분류의 규격 **전부**가 갖는 기본 칸을 정한다
 *   시편 규격의 값에서   그 규격**만** 갖는 칸을 더한다
 *
 * ## 왜 두 층인가
 *
 * **같은 시험 안에서도 시편에 따라 칸이 갈린다.** 인장 평판은 폭·두께를 갖고
 * 환봉은 직경을 갖는다. 규격은 계속 늘어나는데 그때마다 분류의 기본 칸을 늘리면,
 * 안 쓰는 규격에도 빈 칸이 하나씩 쌓이고 그 빈 칸이 "안 쟀다" 인지 "이 규격에
 * 없는 값" 인지 구별되지 않는다.
 *
 * ## 키는 계약이다
 *
 * 이미 저장된 치수가 이 키로 들어 있다. 키를 바꾸면 그 값들이 갈 곳을 잃는다 —
 * 그래서 **만든 뒤에는 못 고친다.** 이름은 얼마든지 고쳐도 된다
 * (`TestType.key`/`label` 을 나눈 것과 같은 관계다).
 */

import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

import { vocabularyApi } from '@/modules/vocabulary/api'
import type { SpecimenField, SpecimenFieldSave, Term } from '@/modules/vocabulary/api'
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
import { useResource } from '@/shared/hooks/useResource'
import { DIMENSIONS, DIMENSION_LABELS, SI_BY_DIMENSION, display } from '@/shared/units'

interface Row extends SpecimenFieldSave {
  /** 이미 저장된 칸인가. **저장된 키는 못 고친다** — 계약이라서. */
  saved: boolean
}

/** 사람이 친 이름에서 키를 만든다. 영문·숫자·밑줄만 남긴다. */
export function keyFrom(label: string): string {
  const cleaned = label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  // 서버가 `^[a-z][a-z0-9_]*$` 를 요구한다. 한글만 친 경우 빈 문자열이 되므로
  // 사람이 직접 키를 채우게 둔다 — 지어내면 `field_1` 같은 것이 쌓인다.
  return /^[a-z]/.test(cleaned) ? cleaned : ''
}

const asRow = (field: SpecimenField | SpecimenFieldSave): Row => ({
  key: field.key,
  label: field.label,
  dimension: field.dimension,
  si_unit: field.si_unit,
  is_required: field.is_required,
  help: field.help ?? null,
  saved: true,
})

export function SpecimenFieldsDialog({
  slug,
  term,
  editsBase,
  onClose,
  onSaved,
}: {
  slug: string
  term: Term
  /**
   * **이 값이 기본 칸을 선언하는 쪽인가.**
   *
   * 전에는 상위 값이 있는지로 가늠했다(`term.parent_value === null`). 그런데
   * **분류를 아직 안 정한 규격**이 있다 — 그러면 규격을 분류로 착각해서, 거기서
   * 만든 칸이 규격의 칸(`extra_fields`)이 아니라 분류 기본 칸 표로 들어갔다.
   * 실제로 개발 DB 에서 그렇게 됐고, 그 칸은 지울 수도 없었다.
   *
   * 역할은 **축**이 정한다(`roleOf`). 값의 상태로 가늠하지 않는다.
   */
  editsBase: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const loaded = useResource(() => vocabularyApi.termFields(slug, term.id), [slug, term.id])
  const [rows, setRows] = useState<Row[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  /**
   * **서버가 준 것만 본다.**
   *
   * 전에는 규격 쪽에서 `term.extra_fields` 를 읽었다 — 그런데 그 `term` 은
   * 목록에서 들고 온 객체라 저장 뒤에도 옛 값 그대로였다. 그래서 칸을 지우고
   * 저장한 뒤 다시 열면 **지운 칸이 되살아나** 있었다.
   *
   * 위에서 온 칸(축·분류)은 여기서 못 고치므로 뺀다. 그 판단이 분류에서든
   * 규격에서든 같아서, 두 모드가 같은 식을 쓴다.
   */
  useEffect(() => {
    setRows((loaded.data ?? []).filter((field) => !field.inherited).map(asRow))
  }, [loaded.data])

  function patch(index: number, change: Partial<Row>) {
    setRows((current) => current.map((row, at) => (at === index ? { ...row, ...change } : row)))
  }

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const fields = rows.map(({ saved: _saved, ...field }) => field)
      if (editsBase) await vocabularyApi.saveCategoryFields(slug, term.id, fields)
      else await vocabularyApi.update(slug, term.id, { extra_fields: fields })
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  /**
   * 상위가 준 칸. **여기서는 못 지운다** — 지우려면 분류에서 고쳐야 한다.
   *
   * 분류에서 열면 `inherited` 가 전부 `false` 다(자기가 선언한 칸이라 여기서
   * 고칠 수 있다). 규격에서 열면 분류가 준 칸이 `true` 로 온다.
   */
  const inherited = (loaded.data ?? []).filter((field) => field.inherited)
  const before = (loaded.data ?? []).filter((field) => !field.inherited)
  const dropped = before.filter((field) => !rows.some((row) => row.key === field.key))

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {term.value} — {editsBase ? '기본 치수 칸' : '이 규격만의 칸'}
          </DialogTitle>
          <DialogDescription>
            {editsBase ? (
              <>
                이 분류의 <b>모든 규격</b>이 이 칸을 갖습니다. <b>최소로 두세요</b> — 그
                분류의 규격이면 예외 없이 갖는 것만. 인장 환봉에는 폭·두께가 없고 DMA
                인장 필름에는 지지 간격이 없습니다.
              </>
            ) : (
              <>
                분류의 기본 칸에 <b>더해지는</b> 칸입니다. 이 규격이 환봉이라 직경이
                필요하다거나, 3점 굽힘이라 지지 간격이 필요할 때 씁니다.
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={loaded.error ?? error} />

        {inherited.length > 0 && (
          <p className="text-muted-foreground rounded-md border p-2.5 text-xs">
            분류 <b>{term.parent_value}</b> 가 준 칸:{' '}
            {inherited.map((field) => field.label).join(' · ')} —{' '}
            <b>여기서는 못 지웁니다.</b> 분류의 기본 칸에서 고치세요.
          </p>
        )}

        <div className="space-y-1.5">
          {rows.map((row, index) => (
            <div
              key={index}
              className="grid grid-cols-[1fr_9rem_8rem_4rem_auto] items-start gap-2"
            >
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
                  /* **키는 계약이다.** 이미 저장된 치수가 이 키로 들어 있어서,
                     바꾸면 그 값들이 갈 곳을 잃는다. */
                  <p className="text-muted-foreground mt-0.5 text-xs">쓰이는 중 · 고정</p>
                )}
              </div>
              <div>
                {/* **차원이 정해지면 저장 단위도 정해진다** — 따로 고를 것이
                    없다. 정의에 mm 라고 적었는데 저장된 숫자가 m 인 상태가
                    만들어지면 화면·계산이 1000배 틀리고, 숫자는 멀쩡해 보인다. */}
                <select
                  aria-label={`${index + 1}번 칸 차원`}
                  className="border-input bg-background h-8 w-full rounded-md border px-2 text-xs"
                  value={row.dimension}
                  onChange={(event) =>
                    patch(index, {
                      dimension: event.target.value,
                      si_unit: SI_BY_DIMENSION[event.target.value] ?? '1',
                    })
                  }
                >
                  {DIMENSIONS.map((item) => (
                    <option key={item} value={item}>
                      {DIMENSION_LABELS[item] ?? item}
                    </option>
                  ))}
                </select>
                {/* **이미 적어 둔 숫자는 안 바뀐다.** 두께 0.001 을 면적으로
                    바꾸면 그 값이 0.001 m² 로 읽힌다 — 오류 없이. */}
                {row.saved && row.dimension !== before.find((f) => f.key === row.key)?.dimension ? (
                  <p className="text-destructive mt-0.5 text-xs">
                    이미 적어 둔 값이 <b>{display(row.si_unit, row.dimension).unit || '수치'}</b>
                    (으)로 읽힙니다 — 다시 확인하세요.
                  </p>
                ) : (
                  <p className="text-muted-foreground mt-0.5 text-xs">
                    화면 {display(row.si_unit, row.dimension).unit || '수치'}
                  </p>
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
          저장은 언제나 그 차원의 SI 이고 화면만 실무 단위로 보입니다(길이는 저장 m ·
          화면 mm). 차원을 바꾸면 <b>이미 적어 둔 숫자는 그대로 둔 채 새 단위로 읽힙니다</b> —
          바꾼 칸은 값을 다시 확인하세요.
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
