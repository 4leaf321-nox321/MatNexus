/**
 * 재료·시료·시편을 **표 하나로 한꺼번에** 등록한다.
 *
 * 판이 하나 들어오면 셋이 같은 순간에 정해진다. 창을 셋 거치게 하면 그 사이에
 * 하나를 빠뜨리고, 빠뜨린 것은 시험 파일이 도착할 때에야 보인다.
 *
 * ## 빈 칸은 위와 같다
 *
 * 재료 칸이 빈 줄은 위 줄의 재료에, 시료 칸이 빈 줄은 위 줄의 시료에 붙는다.
 * 엑셀에서 늘 하는 방식이고, 덕분에 한 재료 아래 시료 여럿·한 시료 아래 시편
 * 여럿이 표에서 그대로 읽힌다. 묶는 규칙은 `bulkRows.group` 하나에만 산다.
 *
 * ## 열은 켜고 끈다
 *
 * 셋을 다 받으면 칸이 스물 몇 개다. 재료만 넣는 날에 시편 칸까지 펼쳐 두면
 * 아무것도 못 읽는다. 그래서 **필요한 열만 켠다.**
 *
 * ## 보내는 것은 한 번
 *
 * 줄마다 요청을 보내면 스무 줄이 예순 번이 되고, 중간에 끊기면 재료만 만들어진
 * 채로 남는다. 서버가 마디마다 세이브포인트를 두고 한 번에 받는다 —
 * **만들 수 있는 것은 만들고, 못 만든 마디는 줄 번호와 이유로 돌아온다.**
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, Columns3, Copy, Plus, Trash2 } from 'lucide-react'

import { materialsApi } from '@/modules/materials/api'
import type { BulkResult } from '@/modules/materials/api'
import {
  COLUMNS,
  MAX_ROWS,
  blankRow,
  blankRows,
  carried,
  group,
  groupLabel,
  has,
  initialShown,
  isEmpty,
  paste,
  problems,
  spreads,
  tally,
  toTsv,
} from '@/modules/materials/bulkRows'
import type { Group, Row } from '@/modules/materials/bulkRows'
import { copyText } from '@/shared/lib/clipboard'
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
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/components/ui/dropdown-menu'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'

const GROUPS: Group[] = ['material', 'sample', 'specimen']

/** 갈래마다 다른 바탕색 — 스물 몇 칸에서 어디까지가 시료인지 눈으로 잡는다. */
const TINT: Record<Group, string> = {
  material: '',
  sample: 'bg-muted/30',
  specimen: 'bg-muted/60',
}

function ColumnPicker({
  shown,
  onChange,
}: {
  shown: Set<string>
  onChange: (next: Set<string>) => void
}) {
  /** 이 갈래가 하나라도 켜져 있나. */
  function on(target: Group): boolean {
    return COLUMNS.some((column) => column.group === target && shown.has(column.key))
  }

  function toggle(key: string) {
    const next = new Set(shown)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    onChange(next)
  }

  function toggleGroup(target: Group) {
    const off = on(target)
    const next = new Set(shown)
    for (const column of COLUMNS.filter((column) => column.group === target)) {
      // 켤 때는 **쓸 만한 것만** 켠다. 아홉 칸을 한꺼번에 펼치면 표가 화면을
      // 벗어나고, 사람은 무엇이 켜졌는지도 모른다.
      if (off) next.delete(column.key)
      else if (column.shown) next.add(column.key)
    }
    onChange(next)
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          <Columns3 className="size-3.5" />열 고르기 ({shown.size})
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-96 w-56 overflow-y-auto">
        {GROUPS.map((target) => (
          <div key={target}>
            {target !== 'material' && <DropdownMenuSeparator />}
            <DropdownMenuLabel className="flex items-center justify-between">
              {groupLabel(target)}
              <button
                type="button"
                aria-label={`${groupLabel(target)} 열 ${on(target) ? '끄기' : '켜기'}`}
                className="text-primary text-xs font-normal hover:underline"
                onClick={(event) => {
                  event.preventDefault()
                  toggleGroup(target)
                }}
              >
                {on(target) ? '끄기' : '켜기'}
              </button>
            </DropdownMenuLabel>
            {COLUMNS.filter((column) => column.group === target).map((column) => (
              <DropdownMenuCheckboxItem
                key={column.key}
                checked={shown.has(column.key)}
                onSelect={(event) => event.preventDefault()}
                onCheckedChange={() => toggle(column.key)}
              >
                {column.label}
              </DropdownMenuCheckboxItem>
            ))}
          </div>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => onChange(initialShown())}>처음으로</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
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
  const [shown, setShown] = useState<Set<string>>(initialShown)
  const [rows, setRows] = useState<Row[]>(blankRows)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [result, setResult] = useState<BulkResult | null>(null)
  /** 복사 직후 잠깐 바뀌는 표시. **아무 반응이 없으면 됐는지 알 수 없다.** */
  const [copied, setCopied] = useState(false)
  const first = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    setRows(blankRows())
    setError(null)
    setResult(null)
    setCopied(false)
    // 열자마자 첫 칸에 적을 수 있어야 한다 — 붙여 넣기가 이 창의 주된 쓰임이다.
    setTimeout(() => first.current?.focus(), 0)
  }, [open])

  const visible = useMemo(
    () => COLUMNS.filter((column) => shown.has(column.key)),
    [shown]
  )
  // 사람이 적은 것과, 위에서 이어받은 것을 채운 것. 화면은 앞을, 검사와
  // 보내기는 뒤를 본다.
  const effective = useMemo(() => carried(rows, visible), [rows, visible])
  const found = useMemo(() => problems(effective, visible), [effective, visible])
  const tree = useMemo(() => group(effective, visible), [effective, visible])
  const counted = useMemo(
    () => tally(tree, effective, visible),
    [tree, effective, visible]
  )
  const bad = Object.keys(found).length
  const filled = rows.filter((row) => !isEmpty(row, visible)).length
  const ready = filled > 0 && bad === 0 && filled <= MAX_ROWS && !busy

  async function copyTable() {
    const done = await copyText(toTsv(rows, visible))
    if (!done) {
      setError(new Error('복사하지 못했습니다. 표를 직접 끌어 골라 복사하세요.'))
      return
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  function edit(at: number, key: string, value: string) {
    setRows((current) => current.map((row, i) => (i === at ? { ...row, [key]: value } : row)))
  }

  async function submit() {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const done = await materialsApi.bulk(tree)
      setResult(done)
      if (done.materials + done.samples + done.specimens > 0) onDone()
      if (done.blocked.length === 0) {
        onClose()
        return
      }
      // **하나도 못 만들었으면 창을 닫지 않는다.** 적어 둔 것이 사라진다.
      // 만들어진 줄만 걷어 내고 문제 있는 줄을 남긴다.
      const stuck = new Set(done.blocked.map((item) => item.row))
      setRows((current) => {
        const left = current.filter((_, at) => stuck.has(at))
        return left.length > 0 ? left : blankRows()
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('등록하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-[min(97vw,84rem)]">
        <DialogHeader>
          <DialogTitle>여러 개 등록</DialogTitle>
          <DialogDescription>
            한 줄이 하나입니다. <b>재료 칸이 빈 줄은 위 줄의 재료에</b>, 시료 칸이 빈 줄은 위
            줄의 시료에 붙습니다 — 한 재료 아래 시료 여럿, 한 시료 아래 시편 여럿을 그렇게
            넣습니다. 엑셀에서 복사해 표에 그대로 붙여 넣을 수 있습니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={error} />

        <div className="flex flex-wrap items-center gap-2">
          <ColumnPicker shown={shown} onChange={setShown} />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setRows((current) => [...current, blankRow()])}
          >
            <Plus className="size-3.5" /> 줄 추가
          </Button>
          {/* **머리글까지 복사한다.** 엑셀에서 이어 쓰다 한 칸 밀린 것을
              알아채지 못하면, 되돌려 붙일 때 두께 자리에 별칭이 들어간다.
              적은 줄이 없어도 눌린다 — 머리글만 받아 엑셀에서 먼저 채우고
              돌아오는 것이 이 기능의 쓰임 절반이다. */}
          <Button variant="outline" size="sm" onClick={copyTable}>
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
            {copied ? '복사했습니다' : '표 복사 (머리글 포함)'}
          </Button>
          <p className="text-muted-foreground text-xs">
            {counted.materials > 0 || counted.samples > 0 ? (
              <>
                재료 <b>{counted.materials}</b> · 시료 <b>{counted.samples}</b> · 시편{' '}
                <b>{counted.specimens}</b>
              </>
            ) : (
              '적은 줄이 없습니다'
            )}
            {counted.implied > 0 && (
              // **말해 주지 않으면 놀란다.** 시편만 적으면 시료가 저절로 생긴다.
              <span> · 시료 {counted.implied}건은 시편 때문에 저절로 만들어집니다</span>
            )}
            {bad > 0 && <span className="text-destructive"> · {bad}줄을 고쳐야 합니다</span>}
          </p>
        </div>

        <div className="rounded-md border">
          <Table className="text-sm">
            <TableHeader className="bg-muted/40">
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-8" />
                {GROUPS.filter((target) =>
                  visible.some((column) => column.group === target)
                ).map((target) => (
                  <TableHead
                    key={target}
                    colSpan={visible.filter((column) => column.group === target).length}
                    className={`border-l text-center text-xs ${TINT[target]}`}
                  >
                    {groupLabel(target)}
                  </TableHead>
                ))}
                <TableHead className="w-8" />
              </TableRow>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-8 text-center text-xs">#</TableHead>
                {visible.map((column, across) => (
                  <TableHead
                    key={column.key}
                    className={`${column.width} text-xs ${TINT[column.group]} ${
                      visible[across - 1]?.group !== column.group ? 'border-l' : ''
                    }`}
                  >
                    {column.label}
                    {column.hint && (
                      <span className="text-muted-foreground font-normal"> ({column.hint})</span>
                    )}
                  </TableHead>
                ))}
                <TableHead className="w-8" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row, at) => {
                // 재료 칸이 채워진 줄이 새 덩이의 시작이다. 얇은 선 하나로
                // 「여기부터 다른 재료」를 보인다.
                const starts = at > 0 && has(row, 'material', visible)
                return (
                  <TableRow
                    key={at}
                    className={`hover:bg-transparent ${starts ? 'border-t-foreground/25 border-t-2' : ''}`}
                  >
                    <TableCell className="text-muted-foreground p-0 text-center text-xs">
                      {at + 1}
                    </TableCell>
                    {visible.map((column, across) => {
                      const why = found[at]?.[column.key]
                      return (
                        <TableCell
                          key={column.key}
                          className={`p-0 ${TINT[column.group]} ${
                            visible[across - 1]?.group !== column.group ? 'border-l' : ''
                          }`}
                        >
                          <input
                            ref={at === 0 && across === 0 ? first : undefined}
                            aria-label={`${at + 1}번 줄 ${groupLabel(column.group)} ${column.label}`}
                            aria-invalid={why ? true : undefined}
                            title={why}
                            inputMode={column.kind === 'number' ? 'decimal' : undefined}
                            value={row[column.key] ?? ''}
                            placeholder={
                              // 이어받은 값은 **흐리게 비쳐 준다.** 안 보이면
                              // 사람은 분류가 비었다고 읽고 줄마다 다시 적는다.
                              (row[column.key] ?? '') === '' && effective[at]?.[column.key]
                                ? effective[at][column.key]
                                : at === 0
                                  ? column.placeholder
                                  : undefined
                            }
                            onChange={(event) => edit(at, column.key, event.target.value)}
                            onPaste={(event) => {
                              const text = event.clipboardData.getData('text')
                              if (!spreads(text)) return
                              // 여러 칸짜리다. 그대로 두면 탭까지 한 칸에 들어간다.
                              event.preventDefault()
                              setRows((current) => paste(current, text, at, across, visible))
                            }}
                            className={`focus:bg-accent/50 h-8 w-full bg-transparent px-2 outline-none ${
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
                        onClick={() => setRows((current) => current.filter((_, i) => i !== at))}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>

        {filled > MAX_ROWS && (
          <p className="text-destructive text-xs">
            한 번에 {MAX_ROWS}줄까지 넣을 수 있습니다. 지금 {filled}줄입니다.
          </p>
        )}

        {result && result.blocked.length > 0 && (
          // **조용히 세지 않는다.** 어느 줄이 왜 막혔는지 말해야 고칠 수 있다.
          <div className="text-xs">
            <p className="mb-1">
              재료 {result.materials} · 시료 {result.samples} · 시편 {result.specimens}건을
              만들었습니다.
            </p>
            <ul className="text-destructive max-h-32 space-y-0.5 overflow-y-auto">
              {result.blocked.map((item) => (
                <li key={`${item.row}-${item.reason}`}>
                  {item.row + 1}번 줄 — {item.reason}
                </li>
              ))}
            </ul>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={submit} disabled={!ready}>
            {busy ? '만드는 중…' : '등록'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
