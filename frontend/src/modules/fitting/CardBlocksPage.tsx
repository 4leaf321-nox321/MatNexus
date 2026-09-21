/**
 * 카드 항목란 — **화면에서 만든다** (ADR 0033).
 *
 * 새 물성 갈래를 카드에 싣고 덱까지 보내려면 조각이 셋인데, 둘은 이미 화면에서
 * 됐고 **가운데만 코드**였다:
 *
 *     ① 항목란(여기)      무엇을 담는 칸인가 — 이름·값·단위
 *     ② 채우는 계산        계산식 화면에서 「넣을 블록」 으로 이 항목란을 고른다
 *     ③ 덱에 쓰는 규칙      내보내기 정의가 `블록.값` 으로 가리킨다
 *
 * 그래서 r값 하나 싣자는 요구에도 배포가 돌았다. 여기까지 데이터가 되면 그 사슬이
 * 화면 안에서 닫힌다.
 *
 * **내장 항목란은 안 보인다** — 코드가 등록하고 여기서 못 고친다. 다만 이름은
 * 아래에 적어 둔다: 같은 키를 쓰려다 저장 단계에서 막히는 것보다 먼저 보는 편이 낫다.
 */

import { useMemo, useState } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'

import { fittingApi } from '@/modules/fitting/api'
import type { CardBlockDef, CardSlot } from '@/modules/fitting/api'
import { testsApi } from '@/modules/tests/api'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { Textarea } from '@/shared/components/ui/textarea'
import { useAuth } from '@/shared/auth/AuthContext'
import { isSystemAdmin } from '@/shared/auth/roles'
import { useResource } from '@/shared/hooks/useResource'

/** 빈 슬롯 한 줄. 단위 기본은 무차원 — 비율·계수가 가장 흔하다. */
const EMPTY: CardSlot = { key: '', label: '', si_unit: '1' }

export default function CardBlocksPage() {
  const { user } = useAuth()
  const canEdit = isSystemAdmin(user)
  const defined = useResource(() => fittingApi.blockDefinitions(), [])
  const all = useResource(() => fittingApi.blocks(), [])
  const [editing, setEditing] = useState<CardBlockDef | null>(null)
  const [making, setMaking] = useState(false)
  const [removing, setRemoving] = useState<CardBlockDef | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const rows = defined.data ?? []
  // **`rows` 가 아니라 원본을 본다.** `rows` 는 렌더마다 새 배열이라 의존성으로
  // 걸면 메모가 매번 깨진다.
  const builtin = useMemo(() => {
    const mine = new Set((defined.data ?? []).map((one) => one.key))
    return (all.data ?? []).filter((one) => !mine.has(one.key))
  }, [all.data, defined.data])

  function reload() {
    defined.reload()
    all.reload()
  }

  async function remove(item: CardBlockDef) {
    setBusy(true)
    setError(null)
    try {
      await fittingApi.removeBlockDefinition(item.id)
      setRemoving(null)
      reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  async function toggle(item: CardBlockDef) {
    setError(null)
    try {
      await fittingApi.updateBlockDefinition(item.id, { enabled: !item.enabled })
      reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('바꾸지 못했습니다.'))
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="카드 항목란"
        description="물성 카드가 담는 칸입니다. 여기서 만들면 배포 없이 카드·계산식·내보내기 정의가 바로 압니다 — 계산식 화면의 「넣을 블록」 목록에 뜨고, 덱 정의는 「키.값」 으로 가리킵니다."
        actions={
          canEdit ? (
            <Button variant="outline" onClick={() => setMaking(true)}>
              <Plus className="size-4" />
              항목란 만들기
            </Button>
          ) : null
        }
      />

      {error ? <ErrorNotice error={error} className="mb-3" /> : null}
      {defined.error ? <ErrorNotice error={defined.error} className="mb-3" /> : null}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>이름</TableHead>
            <TableHead>담는 것</TableHead>
            <TableHead>내는 시험</TableHead>
            <TableHead>쓰는 카드</TableHead>
            <TableHead>상태</TableHead>
            <TableHead className="w-24" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((item) => (
            <TableRow key={item.id}>
              <TableCell>
                <span className="flex flex-wrap items-center gap-2">
                  {item.label}
                  <span className="text-muted-foreground font-mono text-xs">{item.key}</span>
                  <Badge variant="outline">v{item.version}</Badge>
                </span>
              </TableCell>
              <TableCell>
                값 {item.produces.length}
                {item.rows.length > 0 ? ` · 표 열 ${item.rows.length}` : ''}
              </TableCell>
              <TableCell>
                {item.from_tests.length > 0 ? (
                  item.from_tests.join(' · ')
                ) : (
                  <span className="text-muted-foreground">없음</span>
                )}
              </TableCell>
              <TableCell>{item.card_count}</TableCell>
              <TableCell>
                {!item.enabled ? (
                  <Badge variant="outline">꺼짐</Badge>
                ) : item.installed ? (
                  <Badge variant="secondary">쓰는 중</Badge>
                ) : (
                  // 켜 뒀는데 안 얹혔다 = 선언에 탈이 났다. 이유는 기동 로그에 있다.
                  <Badge variant="destructive">못 얹음</Badge>
                )}
              </TableCell>
              <TableCell className="text-right">
                {canEdit ? (
                  <span className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      title="고치기"
                      aria-label={`${item.label} 고치기`}
                      onClick={() => setEditing(item)}
                    >
                      <Pencil className="size-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void toggle(item)}
                      aria-label={`${item.label} ${item.enabled ? '끄기' : '켜기'}`}
                    >
                      {item.enabled ? '끄기' : '켜기'}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      title="삭제"
                      aria-label={`${item.label} 삭제`}
                      onClick={() => setRemoving(item)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </span>
                ) : null}
              </TableCell>
            </TableRow>
          ))}
          {rows.length === 0 && !defined.loading ? (
            <TableRow>
              <TableCell colSpan={6} className="text-muted-foreground py-8 text-center">
                만든 항목란이 없습니다. 내장 항목란만으로 카드가 그려집니다.
              </TableCell>
            </TableRow>
          ) : null}
        </TableBody>
      </Table>

      <section className="mt-8">
        <h2 className="text-sm font-semibold">내장 항목란</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          코드가 등록합니다 — 여기서 고치거나 <b>같은 키로 새로 만들 수 없습니다.</b>
        </p>
        <p className="mt-2 flex flex-wrap gap-1.5">
          {builtin.map((one) => (
            <Badge key={one.key} variant="outline" title={one.help}>
              {one.label}
              <span className="text-muted-foreground ml-1 font-mono text-xs">{one.key}</span>
            </Badge>
          ))}
        </p>
      </section>

      <BlockDialog
        open={making || editing !== null}
        item={editing}
        onClose={() => {
          setMaking(false)
          setEditing(null)
        }}
        onSaved={() => {
          setMaking(false)
          setEditing(null)
          reload()
        }}
      />
      <ConfirmDialog
        open={removing !== null}
        title="항목란을 지웁니다"
        body={
          <p>
            <b>{removing?.label}</b> 을(를) 지웁니다. 이 항목란을 쓰는 계산식·덱 정의가
            있으면 그쪽이 갈 곳을 잃습니다 — 잠깐 멈추려는 것이면 <b>끄기</b>를 쓰세요.
          </p>
        }
        busy={busy}
        onConfirm={() => {
          if (removing) void remove(removing)
        }}
        onClose={() => setRemoving(null)}
      />
    </div>
  )
}

function BlockDialog({
  open,
  item,
  onClose,
  onSaved,
}: {
  open: boolean
  item: CardBlockDef | null
  onClose: () => void
  onSaved: () => void
}) {
  const types = useResource(() => testsApi.types(), [])
  const [key, setKey] = useState('')
  const [label, setLabel] = useState('')
  const [help, setHelp] = useState('')
  const [produces, setProduces] = useState<CardSlot[]>([{ ...EMPTY }])
  const [rows, setRows] = useState<CardSlot[]>([])
  const [fromTests, setFromTests] = useState<string[]>([])
  const [measured, setMeasured] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState<string | null>(null)

  // 열릴 때 한 번만 채운다 — 타이핑 중에 덮어쓰면 글자가 사라진다.
  const seed = item?.id ?? (open ? 'new' : null)
  if (open && seed !== loaded) {
    setLoaded(seed)
    setKey(item?.key ?? '')
    setLabel(item?.label ?? '')
    setHelp(item?.help ?? '')
    setProduces(item ? item.produces.map((one) => ({ ...one })) : [{ ...EMPTY }])
    setRows(item ? item.rows.map((one) => ({ ...one })) : [])
    setFromTests(item?.from_tests ?? [])
    setMeasured(item?.measured ?? false)
    setError(null)
  }
  if (!open && loaded !== null) setLoaded(null)

  async function save() {
    setBusy(true)
    setError(null)
    const clean = (list: CardSlot[]) => list.filter((one) => one.key.trim() !== '')
    try {
      const body = {
        label,
        help,
        produces: clean(produces),
        rows: clean(rows),
        from_tests: fromTests,
        measured,
      }
      if (item) await fittingApi.updateBlockDefinition(item.id, body)
      // 순서는 화면에서 안 고른다 — 만든 것은 내장들 뒤에 선다(서버 기본과 같은 값).
      else await fittingApi.createBlockDefinition({ key, sort_order: 200, ...body })
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{item ? '항목란 고치기' : '항목란 만들기'}</DialogTitle>
          <DialogDescription>
            담는 값에 <b>이름과 SI 단위</b>를 함께 적습니다. 값이 어느 물성인지까지
            적어 두면(물성 키) 문헌값·선언값과 같은 물성으로 묶입니다.
          </DialogDescription>
        </DialogHeader>

        {error ? <ErrorNotice error={error} /> : null}

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="block-key">키</Label>
            <Input
              id="block-key"
              value={key}
              disabled={item !== null}
              placeholder="anisotropy"
              onChange={(event) => setKey(event.target.value)}
            />
            <p className="text-muted-foreground text-xs">
              {item
                ? '카드가 이 키로 값을 들고 있어 못 바꿉니다.'
                : '영소문자·숫자·밑줄. 점은 못 씁니다 — 덱 정의가 「키.값」 으로 가리킵니다.'}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="block-label">이름</Label>
            <Input
              id="block-label"
              value={label}
              placeholder="이방성"
              onChange={(event) => setLabel(event.target.value)}
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="block-help">설명</Label>
          <Textarea
            id="block-help"
            value={help}
            rows={2}
            placeholder="세 방향 인장에서 나오는 r값들."
            onChange={(event) => setHelp(event.target.value)}
          />
        </div>

        <SlotEditor title="담는 값" slots={produces} onChange={setProduces} />
        <SlotEditor
          title="표의 열"
          hint="비우면 이 항목란에는 표가 없습니다."
          slots={rows}
          onChange={setRows}
        />

        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">내는 시험</legend>
          <p className="text-muted-foreground text-xs">
            준비도가 「이 항목란이 없다 → 이 시험을 하면 생긴다」 로 답하는 근거입니다.
          </p>
          <div className="flex flex-wrap gap-2">
            {(types.data ?? []).map((one) => (
              <label key={one.key} className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={fromTests.includes(one.key)}
                  onChange={(event) =>
                    setFromTests((was) =>
                      event.target.checked
                        ? [...was, one.key]
                        : was.filter((key_) => key_ !== one.key),
                    )
                  }
                />
                {one.label}
              </label>
            ))}
          </div>
        </fieldset>

        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={measured}
            onChange={(event) => setMeasured(event.target.checked)}
          />
          <span>
            값이 <b>시험에서 나옵니다</b>
            <span className="text-muted-foreground block text-xs">
              켜면 값 등급을 시편 수로 매깁니다. 사람이 적거나 문헌에서 받는 값이면 끕니다.
            </span>
          </span>
        </label>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            닫기
          </Button>
          <Button disabled={busy || label.trim() === ''} onClick={() => void save()}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function SlotEditor({
  title,
  hint,
  slots,
  onChange,
}: {
  title: string
  hint?: string
  slots: CardSlot[]
  onChange: (next: CardSlot[]) => void
}) {
  function set(index: number, patch: Partial<CardSlot>) {
    onChange(slots.map((one, at) => (at === index ? { ...one, ...patch } : one)))
  }

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">{title}</legend>
      {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
      {slots.map((slot, index) => (
        <div key={index} className="grid gap-2 sm:grid-cols-[1fr_1fr_6rem_1fr_2rem]">
          <Input
            value={slot.key}
            placeholder="r_bar"
            aria-label={`${title} ${index + 1} 키`}
            onChange={(event) => set(index, { key: event.target.value })}
          />
          <Input
            value={slot.label}
            placeholder="평균 이방성"
            aria-label={`${title} ${index + 1} 이름`}
            onChange={(event) => set(index, { label: event.target.value })}
          />
          <Input
            value={slot.si_unit ?? '1'}
            placeholder="1"
            aria-label={`${title} ${index + 1} 단위`}
            onChange={(event) => set(index, { si_unit: event.target.value })}
          />
          <Input
            value={slot.property_key ?? ''}
            placeholder="물성 키(선택)"
            aria-label={`${title} ${index + 1} 물성 키`}
            onChange={(event) => set(index, { property_key: event.target.value })}
          />
          <Button
            variant="ghost"
            size="icon"
            aria-label={`${title} ${index + 1} 줄 지우기`}
            onClick={() => onChange(slots.filter((_, at) => at !== index))}
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={() => onChange([...slots, { ...EMPTY }])}>
        <Plus className="size-4" />줄 추가
      </Button>
    </fieldset>
  )
}
