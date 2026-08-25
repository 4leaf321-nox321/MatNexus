/**
 * 재료를 **여러 개 한꺼번에** 등록한다 — 표로.
 *
 * 한 판에 같은 Family·Category 로 열 몇 개를 넣는 일이 실제 작업이다. 창을
 * 열고 닫기를 열 번 하면 그 자체가 일이 되고, 그러다 하나를 빠뜨린다.
 *
 * ## 공통은 위에, 다른 것만 줄로
 *
 * Family·Category·적용 제품·부위는 대개 같다. 그것을 줄마다 적게 하면 **오타
 * 하나가 분류를 갈라 놓고**, 그때 목록이 두 덩이로 보인다. 다만 줄에 적은 값이
 * 이긴다 — 한 판에 부위가 다른 것이 하나 섞이는 일은 늘 있다.
 *
 * ## 이름은 서버가 만든다
 *
 * 화면이 규칙을 다시 구현하지 않는다(ADR 0004). 여기서는 재료를 하나씩 만들고
 * 서버가 붙인 이름을 그대로 받는다 — 미리 보여 주려면 줄마다 서버에 물어야
 * 하는데, 스무 줄이면 스무 번이다. 대신 **같은 이름이 될 줄끼리는 표에서 짚는다**
 * (`bulkRows.problems`).
 *
 * ## 한 줄이 막혀도 나머지는 만든다
 *
 * 열 줄 중 셋째가 이미 있는 이름이라 전부 실패하면, 사람은 무엇이 문제인지
 * 모른 채 다시 적어야 한다. **만들 수 있는 것은 만들고, 못 만든 줄은 이유와
 * 함께 남긴다.** 그리고 **성공한 줄은 표에서 지운다** — 안 지우면 다시 눌렀을
 * 때 같은 재료를 또 만들려 든다.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

import { DENSITY_UNIT, LENGTH_UNIT, materialsApi } from '@/modules/materials/api'
import {
  COLUMNS,
  blankRow,
  blankRows,
  isEmpty,
  numberOf,
  paste,
  problems,
  spreads,
  textOf,
} from '@/modules/materials/bulkRows'
import type { Row } from '@/modules/materials/bulkRows'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'

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
  const [category, setCategory] = useState('Steel')
  const [product, setProduct] = useState('')
  const [part, setPart] = useState('')
  const [rows, setRows] = useState<Row[]>(blankRows)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [blocked, setBlocked] = useState<string[]>([])
  const first = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    setRows(blankRows())
    setError(null)
    setBlocked([])
    // 열자마자 첫 칸에 적을 수 있어야 한다 — 붙여 넣기가 이 창의 주된 쓰임이다.
    setTimeout(() => first.current?.focus(), 0)
  }, [open])

  const filled = useMemo(() => rows.filter((row) => !isEmpty(row)), [rows])
  const found = useMemo(() => problems(rows), [rows])
  const bad = Object.keys(found).length
  const ready = filled.length > 0 && bad === 0 && Boolean(category) && !busy

  function edit(at: number, key: string, value: string) {
    setRows((current) => current.map((row, i) => (i === at ? { ...row, [key]: value } : row)))
  }

  async function submit() {
    setBusy(true)
    setError(null)
    const failed: string[] = []
    const made: Row[] = []

    for (const row of filled) {
      try {
        await materialsApi.create({
          family,
          category,
          grade: row.grade.trim(),
          details: textOf(row, 'details'),
          spec_thickness: numberOf(row, 'spec_thickness'),
          spec_thickness_unit: LENGTH_UNIT,
          alias: textOf(row, 'alias'),
          // 줄에 적었으면 그것이, 아니면 위에서 고른 것이 간다.
          applied_product: textOf(row, 'applied_product') ?? (product || null),
          applied_part: textOf(row, 'applied_part') ?? (part || null),
          density: numberOf(row, 'density'),
          density_unit: DENSITY_UNIT,
          poisson_ratio: numberOf(row, 'poisson_ratio'),
        })
        made.push(row)
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
    if (made.length > 0) onDone()
    if (failed.length === 0) {
      onClose()
      return
    }
    // **하나도 못 만들었으면 창을 닫지 않는다.** 적어 둔 것이 사라진다.
    // 만들어진 줄만 걷어 내고 문제 있는 줄을 남긴다.
    setRows((current) => {
      const left = current.filter((row) => !made.includes(row))
      return left.length > 0 ? left : blankRows()
    })
    setError(new Error(`${made.length}건을 만들었습니다. ${failed.length}건은 못 만들었습니다.`))
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-[min(96vw,72rem)]">
        <DialogHeader>
          <DialogTitle>재료 여러 개 등록</DialogTitle>
          <DialogDescription>
            한 줄이 재료 하나입니다. <b>엑셀에서 복사해 표에 그대로 붙여 넣을 수 있습니다</b> —
            붙여 넣은 자리부터 채워지고 줄이 모자라면 늘어납니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={error} />

        <div className="grid grid-cols-4 gap-3">
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
            label="적용 제품 (모든 줄)"
            value={product}
            onChange={setProduct}
          />
          <VocabularyField
            slug="part"
            label="적용 부위 (모든 줄)"
            value={part}
            onChange={setPart}
          />
        </div>

        <div className="rounded-md border">
          <Table className="text-sm">
            <TableHeader className="bg-muted/50">
              <TableRow>
                <TableHead className="w-10 text-center text-xs">#</TableHead>
                {COLUMNS.map((column) => (
                  <TableHead key={column.key} className={`${column.width} text-xs`}>
                    {column.label}
                    {column.hint && (
                      <span className="text-muted-foreground font-normal"> ({column.hint})</span>
                    )}
                    {column.key === 'grade' && <span className="text-destructive"> *</span>}
                  </TableHead>
                ))}
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row, at) => (
                <TableRow key={at} className="hover:bg-transparent">
                  <TableCell className="text-muted-foreground p-0 text-center text-xs">
                    {at + 1}
                  </TableCell>
                  {COLUMNS.map((column, across) => {
                    const why = found[at]?.[column.key]
                    return (
                      <TableCell key={column.key} className="p-0">
                        <input
                          ref={at === 0 && across === 0 ? first : undefined}
                          aria-label={`${at + 1}번 줄 ${column.label}`}
                          aria-invalid={why ? true : undefined}
                          title={why}
                          inputMode={column.kind === 'number' ? 'decimal' : undefined}
                          value={row[column.key] ?? ''}
                          placeholder={at === 0 ? column.placeholder : undefined}
                          onChange={(event) => edit(at, column.key, event.target.value)}
                          onPaste={(event) => {
                            const text = event.clipboardData.getData('text')
                            if (!spreads(text)) return
                            // 여러 칸짜리다. 그대로 두면 탭까지 한 칸에 들어간다.
                            event.preventDefault()
                            setRows((current) => paste(current, text, at, across))
                          }}
                          className={`focus:bg-accent/40 h-8 w-full bg-transparent px-2 outline-none ${
                            why ? 'text-destructive bg-destructive/10' : ''
                          }`}
                        />
                      </TableCell>
                    )
                  })}
                  <TableCell className="p-0 text-center">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-7"
                      aria-label={`${at + 1}번 줄 지우기`}
                      disabled={rows.length === 1}
                      onClick={() =>
                        setRows((current) => current.filter((_, i) => i !== at))
                      }
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setRows((current) => [...current, blankRow()])}
          >
            <Plus className="size-3.5" /> 줄 추가
          </Button>
          <p className="text-muted-foreground text-xs">
            {filled.length > 0 ? <b>{filled.length}건</b> : '적은 줄이 없습니다'}
            {filled.length > 0 && '을 만듭니다'}
            {bad > 0 && <span className="text-destructive"> · {bad}줄을 고쳐야 합니다</span>}
            {' · 이름은 서버가 규칙대로 붙입니다.'}
          </p>
        </div>

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
          <Button onClick={submit} disabled={!ready}>
            {busy ? '만드는 중…' : `${filled.length || ''}건 등록`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
