/**
 * 재료를 **여러 개 한꺼번에** 등록한다.
 *
 * 한 판에 같은 Family·Category 로 열 몇 개를 넣는 일이 실제 작업이다. 창을
 * 열고 닫기를 열 번 하면 그 자체가 일이 되고, 그러다 하나를 빠뜨린다.
 *
 * ## 공통은 위에, 다른 것만 줄로
 *
 * Family·Category·적용 제품·부위는 대개 같다. 그것을 줄마다 적게 하면 **오타
 * 하나가 분류를 갈라 놓고**, 그때 목록이 두 덩이로 보인다.
 *
 * ## 이름은 서버가 만든다
 *
 * 화면이 규칙을 다시 구현하지 않는다(ADR 0004). 여기서는 재료를 하나씩 만들고
 * 서버가 붙인 이름을 그대로 받는다 — 미리 보여 주려면 줄마다 서버에 물어야
 * 하는데, 스무 줄이면 스무 번이다.
 *
 * ## 한 줄이 막혀도 나머지는 만든다
 *
 * 열 줄 중 셋째가 이미 있는 이름이라 전부 실패하면, 사람은 무엇이 문제인지
 * 모른 채 다시 적어야 한다. **만들 수 있는 것은 만들고, 못 만든 줄은 이유와
 * 함께 남긴다.**
 */

import { useEffect, useState } from 'react'

import { DENSITY_UNIT, LENGTH_UNIT, materialsApi } from '@/modules/materials/api'
import { VocabularyField } from '@/modules/vocabulary/VocabularyField'
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
import { Textarea } from '@/shared/components/ui/textarea'

/** 한 줄이 만드는 재료 하나. */
interface Row {
  grade: string
  details: string
  thickness: number | null
  problem?: string
}

/**
 * `SECC, MDOI, 1.0` → 한 줄.
 *
 * 쉼표·탭 둘 다 받는다 — **엑셀에서 붙여 넣으면 탭이 온다.** 그것을 안 받으면
 * 사람은 한 줄이 통째로 Grade 가 된 것을 보고서야 안다.
 */
export function parseRows(text: string): Row[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [grade = '', details = '', thickness = ''] = line
        .split(/[\t,]/)
        .map((part) => part.trim())
      const size = thickness === '' ? null : Number(thickness)
      return {
        grade,
        details,
        thickness: size,
        problem: !grade
          ? 'Grade 가 비어 있습니다'
          : thickness !== '' && !Number.isFinite(size)
            ? `두께가 숫자가 아닙니다: ${thickness}`
            : undefined,
      }
    })
}

export function BulkMaterialDialog({
  open,
  onClose,
  onDone,
}: {
  open: boolean
  onClose: () => void
  onDone: () => void
}) {
  const [family, setFamily] = useState('Metal')
  const [category, setCategory] = useState('')
  const [product, setProduct] = useState('')
  const [part, setPart] = useState('')
  const [density, setDensity] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [blocked, setBlocked] = useState<string[]>([])

  useEffect(() => {
    if (open) {
      setText('')
      setError(null)
      setBlocked([])
    }
  }, [open])

  const rows = parseRows(text)
  const bad = rows.filter((row) => row.problem)
  const ready = rows.length > 0 && bad.length === 0 && Boolean(category)

  async function submit() {
    setBusy(true)
    setError(null)
    const failed: string[] = []
    let made = 0
    for (const row of rows) {
      try {
        await materialsApi.create({
          family,
          category,
          grade: row.grade,
          details: row.details || null,
          spec_thickness: row.thickness,
          spec_thickness_unit: LENGTH_UNIT,
          applied_product: product || null,
          applied_part: part || null,
          density: density === '' ? null : Number(density),
          density_unit: DENSITY_UNIT,
        })
        made += 1
      } catch (caught) {
        failed.push(
          `${row.grade}${row.details ? ` ${row.details}` : ''} — ${
            caught instanceof Error ? caught.message : '실패'
          }`
        )
      }
    }
    setBusy(false)
    setBlocked(failed)
    if (failed.length === 0) {
      onDone()
      onClose()
      return
    }
    // **하나도 못 만들었으면 창을 닫지 않는다.** 적어 둔 것이 사라진다.
    setError(new Error(`${made}건을 만들었습니다. ${failed.length}건은 못 만들었습니다.`))
    if (made > 0) onDone()
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>재료 여러 개 등록</DialogTitle>
          <DialogDescription>
            같은 Family·Category 안에서 <b>Grade 만 다른 재료</b>를 한 번에 넣습니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={error} />

        <div className="grid grid-cols-2 gap-3">
          <VocabularyField slug="family" label="Family" value={family} onChange={setFamily} />
          <VocabularyField
            slug="category"
            label="Category"
            value={category}
            parentValue={family}
            onChange={setCategory}
          />
          <VocabularyField
            slug="product"
            label="적용 제품"
            value={product}
            onChange={setProduct}
          />
          <VocabularyField slug="part" label="적용 부위" value={part} onChange={setPart} />
          <div className="space-y-1.5">
            <Label htmlFor="bulk-density">밀도 ({DENSITY_UNIT})</Label>
            <Input
              id="bulk-density"
              value={density}
              inputMode="decimal"
              placeholder="비워도 됩니다"
              onChange={(event) => setDensity(event.target.value)}
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="bulk-rows">한 줄에 하나씩</Label>
          <Textarea
            id="bulk-rows"
            rows={8}
            className="font-mono text-xs"
            placeholder={'SECC, MDOI, 1.0\nSGCC, MDOI, 1.2\nSPCC, , 0.8'}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <p className="text-muted-foreground text-xs">
            <b>Grade, 상세, 두께({LENGTH_UNIT})</b> 순입니다. 쉼표나 탭으로 나눕니다 — 엑셀에서
            그대로 붙여 넣어도 됩니다. 이름은 서버가 규칙대로 붙입니다.
          </p>
        </div>

        {rows.length > 0 && (
          <div className="rounded-md border p-3 text-sm">
            <p className="mb-1 text-xs">
              <b>{rows.length}건</b>을 만듭니다
              {bad.length > 0 && (
                <span className="text-destructive"> · {bad.length}건은 고쳐야 합니다</span>
              )}
            </p>
            <ul className="max-h-40 space-y-0.5 overflow-y-auto font-mono text-xs">
              {rows.map((row, at) => (
                <li key={at} className={row.problem ? 'text-destructive' : ''}>
                  {row.grade || '(Grade 없음)'}
                  {row.details ? ` · ${row.details}` : ''}
                  {row.thickness != null ? ` · ${row.thickness}${LENGTH_UNIT}` : ''}
                  {row.problem ? ` — ${row.problem}` : ''}
                </li>
              ))}
            </ul>
          </div>
        )}

        {blocked.length > 0 && (
          // **조용히 세지 않는다.** 무엇이 안 만들어졌는지 말해야 다시 적을 수 있다.
          <ul className="text-destructive max-h-32 space-y-0.5 overflow-y-auto text-xs">
            {blocked.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={submit} disabled={!ready || busy}>
            {busy ? '만드는 중…' : `${rows.length || ''}건 등록`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
