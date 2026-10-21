/**
 * 적용 부품 — **이 재료가 들어가는 부품의 줄**(ADR 0064, 2026-10-21).
 *
 * 전에는 재료 머리에 「적용 제품」 · 「적용 파트」 칩이 스무 개까지 있었다. 사용자 보고: 한
 * 재료가 부품 50개에 들어가면 그 화면과 구조로는 대응이 안 된다 — 어느 제품의 어느 파트인지,
 * 부품코드 · 사업부를 적을 자리도 없었다. BOM 에서 오는 것은 그 넷이 한 줄이다.
 *
 * 그래서 표다. **찾고 거르고 쪽을 나누는 것은 서버다** — 부품 수백 개를 받아 화면에서 거르면
 * 이 쪽에 실린 것만 걸러진다. 넣기는 엑셀 범위 붙여넣기가 기본이고 **미리보기를 거친다** — 같은
 * BOM 을 두 번 붙여넣는 것이 가장 흔한 실수라, 이미 있는 줄을 먼저 보인다.
 */

import { useEffect, useMemo, useState } from 'react'
import { ClipboardPaste, FileSpreadsheet, Pencil, Plus, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { materialsApi } from '@/modules/materials/api'
import type { MaterialPart, MaterialPartPlan } from '@/modules/materials/api'
import {
  changesOf,
  formOf,
  linesOf,
  PART_FIELDS,
  SOURCE_LABELS,
} from '@/modules/materials/partsPaste'
import type { LineForm } from '@/modules/materials/partsPaste'
import { PartsPasteFields, usePartsPaste } from '@/modules/materials/PartsPasteFields'
import { VocabularyField } from '@/modules/vocabulary/VocabularyField'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { EmptyState } from '@/shared/components/EmptyState'
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'

/** 한 쪽의 줄 수. 서버 상한(200) 안쪽 — 눈으로 훑을 만큼. */
const PAGE = 50

/** 재료 화면에서는 재료가 정해져 있다 — 재질 칸이 없다. */
const LINE_FIELDS = PART_FIELDS.filter((one) => one.key !== 'material')

const STATUS_LABELS: Record<string, string> = {
  new: '새로',
  exists: '이미 있음',
  error: '못 넣음',
}

function Value({ text }: { text?: string | null }) {
  if (!text) return <span className="text-muted-foreground">—</span>
  return <>{text}</>
}

export function MaterialPartsTab({
  materialId,
  editable,
  lockedTitle,
  onChanged,
}: {
  materialId: string
  /** 그 재료를 고칠 수 있는가(ADR 0035) — 판정은 서버, 여기는 단추를 미리 잠근다. */
  editable: boolean
  lockedTitle?: string
  /** 줄이 바뀌면 재료 머리의 이름 목록 · 개수도 바뀐다 — 다시 읽게 알린다. */
  onChanged: () => void
}) {
  const [typed, setTyped] = useState('')
  const [q, setQ] = useState('')
  const [division, setDivision] = useState('')
  const [product, setProduct] = useState('')
  const [offset, setOffset] = useState(0)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [pasting, setPasting] = useState(false)
  const [editing, setEditing] = useState<MaterialPart | 'new' | null>(null)
  const [removing, setRemoving] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // 치는 동안 글자마다 부르지 않는다. **거르면 첫 쪽으로** — 3쪽을 보다 거르면 걸러진 결과의
  // 3쪽이 나와 「없다」 로 보인다. **글자가 바뀌었을 때만** — 처음 그릴 때도 돌면 그 사이 넘긴
  // 쪽이 첫 쪽으로 튄다(느린 머신의 시험에서 드러났다).
  useEffect(() => {
    const next = typed.trim()
    if (next === q) return
    const timer = window.setTimeout(() => {
      setQ(next)
      setOffset(0)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [typed, q])

  const page = useResource(
    () =>
      materialsApi.parts(materialId, {
        q: q || undefined,
        division: division || undefined,
        product: product || undefined,
        limit: PAGE,
        offset,
      }),
    [materialId, q, division, product, offset]
  )
  const rows = page.data?.items ?? []
  const total = page.data?.total ?? 0
  const filtered = Boolean(q || division || product)
  const allPicked = rows.length > 0 && rows.every((row) => picked.has(row.id))

  function changed(message: string) {
    setPicked(new Set())
    setNotice(message)
    page.reload()
    onChanged()
  }

  async function remove() {
    setBusy(true)
    setError(null)
    try {
      const done = await materialsApi.removeParts(materialId, [...picked])
      setRemoving(false)
      changed(`${done.removed}줄을 지웠습니다.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1">
          <Label htmlFor="parts-find" className="text-muted-foreground text-xs">
            찾기
          </Label>
          <Input
            id="parts-find"
            className="h-9 w-56"
            placeholder="파트명 · 부품코드 · 제품"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
          />
        </div>
        {/* **고를 값은 그 재료 전체에서** 센다(서버의 `divisions`) — 거른 결과에서 세면 하나를
            고르는 순간 나머지 선택지가 사라져 되돌아갈 길이 없다. */}
        <div className="space-y-1">
          <Label htmlFor="parts-division" className="text-muted-foreground text-xs">
            사업부
          </Label>
          <select
            id="parts-division"
            className="border-input bg-background h-9 rounded-md border px-2 text-sm"
            value={division}
            onChange={(event) => {
              setDivision(event.target.value)
              setOffset(0)
            }}
          >
            <option value="">전체</option>
            {(page.data?.divisions ?? []).map((one) => (
              <option key={one.value} value={one.value}>
                {one.value} ({one.count})
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="parts-product" className="text-muted-foreground text-xs">
            제품
          </Label>
          <select
            id="parts-product"
            className="border-input bg-background h-9 max-w-56 rounded-md border px-2 text-sm"
            value={product}
            onChange={(event) => {
              setProduct(event.target.value)
              setOffset(0)
            }}
          >
            <option value="">전체</option>
            {(page.data?.products ?? []).map((one) => (
              <option key={one.value} value={one.value}>
                {one.value} ({one.count})
              </option>
            ))}
          </select>
        </div>

        <div className="ml-auto flex flex-wrap gap-2">
          {picked.size > 0 && (
            <Button
              variant="outline"
              disabled={!editable}
              title={lockedTitle}
              onClick={() => setRemoving(true)}
            >
              <Trash2 className="size-4" />
              고른 {picked.size}줄 지우기
            </Button>
          )}
          {/* **여러 재료에 걸친 BOM 은 따로 연다** — 재질로 재료를 찾아 재료마다 나눠 넣는다. */}
          <Button variant="outline" asChild>
            <Link to="/materials/parts-import">
              <FileSpreadsheet className="size-4" />
              BOM 가져오기
            </Link>
          </Button>
          <Button
            variant="outline"
            disabled={!editable}
            title={lockedTitle}
            onClick={() => setEditing('new')}
          >
            <Plus className="size-4" />한 줄 추가
          </Button>
          <Button disabled={!editable} title={lockedTitle} onClick={() => setPasting(true)}>
            <ClipboardPaste className="size-4" />
            붙여넣기
          </Button>
        </div>
      </div>

      <ErrorNotice error={page.error ?? error} />
      {notice && <p className="text-sm">{notice}</p>}

      {!page.loading && total === 0 && !filtered ? (
        <EmptyState
          title="적용 부품이 없습니다."
          hint="엑셀에서 BOM 범위를 복사해 「붙여넣기」 로 여러 줄을 한 번에 넣습니다. 여러 재료에 걸친 BOM 은 「BOM 가져오기」 가 재질로 재료를 찾아 나눠 넣습니다."
        />
      ) : (
        <div className="rounded-md border">
          <Table className="text-sm">
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <input
                    type="checkbox"
                    aria-label="이 쪽 전부 선택"
                    checked={allPicked}
                    onChange={(event) => {
                      const next = new Set(picked)
                      for (const row of rows) {
                        if (event.target.checked) next.add(row.id)
                        else next.delete(row.id)
                      }
                      setPicked(next)
                    }}
                  />
                </TableHead>
                <TableHead>파트명</TableHead>
                <TableHead>제품</TableHead>
                <TableHead>부품코드</TableHead>
                <TableHead>사업부</TableHead>
                <TableHead>출처</TableHead>
                <TableHead>비고</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <input
                      type="checkbox"
                      aria-label={`${row.part ?? row.part_code ?? row.product ?? '줄'} 선택`}
                      checked={picked.has(row.id)}
                      onChange={(event) => {
                        const next = new Set(picked)
                        if (event.target.checked) next.add(row.id)
                        else next.delete(row.id)
                        setPicked(next)
                      }}
                    />
                  </TableCell>
                  <TableCell>
                    <Value text={row.part} />
                  </TableCell>
                  <TableCell>
                    <Value text={row.product} />
                  </TableCell>
                  <TableCell className="font-mono">
                    <Value text={row.part_code} />
                  </TableCell>
                  <TableCell>
                    <Value text={row.division} />
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-1.5">
                      <Badge variant="outline" className="font-normal">
                        {SOURCE_LABELS[row.source] ?? row.source}
                      </Badge>
                      {row.source_ref}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Value text={row.note} />
                  </TableCell>
                  <TableCell>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7"
                      aria-label={`${row.part ?? row.part_code ?? '줄'} 고치기`}
                      disabled={!editable}
                      title={lockedTitle}
                      onClick={() => setEditing(row)}
                    >
                      <Pencil className="size-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!page.loading && rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-muted-foreground py-8 text-center">
                    걸러진 줄이 없습니다.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      )}

      {total > PAGE && (
        <div className="flex items-center justify-end gap-2 text-sm">
          <span className="text-muted-foreground tabular-nums">
            {offset + 1}–{Math.min(offset + PAGE, total)} / {total.toLocaleString('ko-KR')}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE))}
          >
            이전
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={offset + PAGE >= total}
            onClick={() => setOffset(offset + PAGE)}
          >
            다음
          </Button>
        </div>
      )}

      <PastePartsDialog
        materialId={materialId}
        open={pasting}
        onClose={() => setPasting(false)}
        onDone={(plan) => {
          setPasting(false)
          changed(
            `${plan.new}줄을 넣었습니다.` +
              (plan.exists ? ` 이미 있던 ${plan.exists}줄은 넘겼습니다.` : '')
          )
        }}
      />
      {editing && (
        <PartLineDialog
          materialId={materialId}
          row={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onDone={(message) => {
            setEditing(null)
            changed(message)
          }}
        />
      )}
      <ConfirmDialog
        open={removing}
        title="적용 부품 줄 지우기"
        body={`고른 ${picked.size}줄을 지웁니다. 재료 · 기준정보 값은 그대로 남습니다.`}
        busy={busy}
        onConfirm={() => void remove()}
        onClose={() => setRemoving(false)}
      />
    </div>
  )
}

/** 미리보기에 보이는 줄 수 — 2,000줄을 다 그리지 않는다. 못 넣는 줄을 먼저. */
const PLAN_SHOWN = 200

function PastePartsDialog({
  materialId,
  open,
  onClose,
  onDone,
}: {
  materialId: string
  open: boolean
  onClose: () => void
  onDone: (plan: MaterialPartPlan) => void
}) {
  const paste = usePartsPaste(LINE_FIELDS)
  const [division, setDivision] = useState('')
  const [sourceRef, setSourceRef] = useState('')
  const [plan, setPlan] = useState<{ key: string; plan: MaterialPartPlan } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const lines = useMemo(() => linesOf(paste.records, division), [paste.records, division])
  const key = JSON.stringify(lines)
  // **붙여넣은 것을 고치면 미리보기는 낡는다** — 낡은 미리보기로 넣으면 본 것과 다른 것이 들어간다.
  const fresh = plan !== null && plan.key === key ? plan.plan : null

  async function run(dryRun: boolean) {
    setBusy(true)
    setError(null)
    try {
      const done = await materialsApi.addParts(materialId, lines, {
        dryRun,
        sourceRef: sourceRef.trim() || null,
      })
      if (dryRun) setPlan({ key, plan: done })
      else {
        setPlan(null)
        paste.setText('')
        onDone(done)
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('넣지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const shown = fresh
    ? [...fresh.rows].sort((a, b) => Number(a.status === 'new') - Number(b.status === 'new'))
    : []

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>적용 부품 붙여넣기</DialogTitle>
          <DialogDescription>
            엑셀에서 머리글과 함께 범위를 복사해 붙여넣습니다. 열마다 무엇인지 확인하고 미리보기로
            새 줄 · 이미 있는 줄을 본 뒤 넣습니다.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[65vh] space-y-3 overflow-y-auto pr-1">
          <PartsPasteFields
            paste={paste}
            fields={LINE_FIELDS}
            placeholder={'파트명\t제품\t부품코드\t사업부\n도어 이너\t냉장고 A\tP-100\t가전'}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="parts-paste-division">사업부(칸이 빈 줄에)</Label>
              <Input
                id="parts-paste-division"
                value={division}
                onChange={(event) => setDivision(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="parts-paste-ref">출처(어느 BOM · 표)</Label>
              <Input
                id="parts-paste-ref"
                placeholder="예: 냉장고 A BOM 2026-10"
                value={sourceRef}
                onChange={(event) => setSourceRef(event.target.value)}
              />
            </div>
          </div>

          <ErrorNotice error={error} />

          {fresh && (
            <div className="space-y-2">
              <div className="flex flex-wrap gap-2 text-sm">
                <Badge>새로 {fresh.new}</Badge>
                <Badge variant="secondary">이미 있음 {fresh.exists}</Badge>
                {fresh.errors > 0 && <Badge variant="destructive">못 넣음 {fresh.errors}</Badge>}
              </div>
              <div className="rounded-md border">
                <Table className="text-xs">
                  <TableHeader>
                    <TableRow>
                      <TableHead>줄</TableHead>
                      <TableHead>판정</TableHead>
                      <TableHead>파트명</TableHead>
                      <TableHead>제품</TableHead>
                      <TableHead>부품코드</TableHead>
                      <TableHead>사업부</TableHead>
                      <TableHead>이유</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {shown.slice(0, PLAN_SHOWN).map((row) => (
                      <TableRow key={row.index}>
                        <TableCell className="tabular-nums">{row.index + 1}</TableCell>
                        <TableCell>
                          <Badge variant={row.status === 'new' ? 'default' : 'outline'}>
                            {STATUS_LABELS[row.status] ?? row.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Value text={row.part} />
                        </TableCell>
                        <TableCell>
                          <Value text={row.product} />
                        </TableCell>
                        <TableCell className="font-mono">
                          <Value text={row.part_code} />
                        </TableCell>
                        <TableCell>
                          <Value text={row.division} />
                        </TableCell>
                        <TableCell>
                          <Value text={row.reason} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {shown.length > PLAN_SHOWN && (
                <p className="text-muted-foreground text-xs">
                  {PLAN_SHOWN}줄까지 보입니다(전체 {shown.length.toLocaleString('ko-KR')}줄) — 못
                  넣는 줄이 먼저 섭니다.
                </p>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            닫기
          </Button>
          <Button
            variant="outline"
            disabled={busy || lines.length === 0}
            onClick={() => void run(true)}
          >
            미리보기
          </Button>
          <Button disabled={busy || !fresh || fresh.new === 0} onClick={() => void run(false)}>
            {fresh ? `${fresh.new}줄 넣기` : '넣기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function PartLineDialog({
  materialId,
  row,
  onClose,
  onDone,
}: {
  materialId: string
  row: MaterialPart | null
  onClose: () => void
  onDone: (message: string) => void
}) {
  const [form, setForm] = useState<LineForm>(() => formOf(row))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const set = (key: keyof LineForm) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }))

  async function save() {
    setBusy(true)
    setError(null)
    try {
      if (row) {
        const changes = changesOf(row, form)
        if (Object.keys(changes).length > 0) {
          await materialsApi.updatePart(materialId, row.id, changes)
        }
        onDone('줄을 고쳤습니다.')
        return
      }
      const done = await materialsApi.addParts(
        materialId,
        [
          {
            part: form.part.trim() || null,
            product: form.product.trim() || null,
            part_code: form.part_code.trim() || null,
            division: form.division.trim() || null,
            note: form.note.trim() || null,
          },
        ],
        { dryRun: false }
      )
      // **넣지 못한 이유를 말한다** — 이미 있는 줄을 「넣었습니다」 로 닫으면 사람은 두 줄이 된 줄 안다.
      const first = done.rows[0]
      if (done.new === 0) {
        setError(new Error(first?.reason ?? '넣지 못했습니다.'))
        return
      }
      onDone('한 줄을 넣었습니다.')
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{row ? '적용 부품 줄 고치기' : '적용 부품 한 줄 추가'}</DialogTitle>
          <DialogDescription>
            파트명 · 제품 · 부품코드 중 하나는 있어야 합니다. 파트명 · 제품 · 사업부는 기준정보 값으로
            묶입니다.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <VocabularyField slug="part" label="파트명" value={form.part} onChange={set('part')} />
          <VocabularyField
            slug="product"
            label="제품"
            value={form.product}
            onChange={set('product')}
          />
          <div className="space-y-1.5">
            <Label htmlFor="part-line-code">부품코드</Label>
            <Input
              id="part-line-code"
              value={form.part_code}
              onChange={(event) => set('part_code')(event.target.value)}
            />
          </div>
          <VocabularyField
            slug="division"
            label="사업부"
            value={form.division}
            onChange={set('division')}
          />
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="part-line-note">비고</Label>
            <Input
              id="part-line-note"
              value={form.note}
              onChange={(event) => set('note')(event.target.value)}
            />
          </div>
        </div>
        <ErrorNotice error={error} />
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            취소
          </Button>
          <Button disabled={busy} onClick={() => void save()}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
