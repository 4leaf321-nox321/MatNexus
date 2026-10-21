/**
 * BOM 가져오기 — **부품표 한 장을 재질로 나눠 재료마다 적용 부품 줄로**(ADR 0064).
 *
 * 부품 정보는 BOM 에서 온다(사용자, 2026-10-21). BOM 한 장에는 재료가 여럿 섞여 있어, 재료
 * 화면마다 붙여넣게 하면 같은 표를 재질별로 잘라 열 번 붙여넣어야 한다. 여기서는 재질 칸으로
 * 재료를 찾는다(BOM 덱이 기억한 짝 → 재료 이름 → 별칭 → Grade).
 *
 * **고르는 것은 사람이다.** 재질이 재료 여럿에 맞거나 못 찾으면 그 재질만 따로 모아 고르게
 * 한다 — 이름이 비슷하다고 서버가 고르면 그 부품은 조용히 다른 재료의 것이 된다. 고칠 권한이
 * 없는 재료의 줄은 이유와 함께 남기고 **나머지는 넣는다**.
 */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { materialsApi } from '@/modules/materials/api'
import type { BomPartImport, BomPartRowIn, Material } from '@/modules/materials/api'
import { MaterialPicker } from '@/modules/materials/MaterialPicker'
import { BOM_STATUS_LABELS, merge, PART_FIELDS, pending } from '@/modules/materials/partsPaste'
import type { MaterialAsk, MaterialChoice } from '@/modules/materials/partsPaste'
import { PartsPasteFields, usePartsPaste } from '@/modules/materials/PartsPasteFields'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { RecordName } from '@/shared/components/RecordName'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
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

/** 보이는 줄 수 — 2,000줄을 다 그리지 않는다. 못 넣는 줄이 먼저 선다. */
const SHOWN = 200

type Choice = MaterialChoice
type Ask = MaterialAsk

export default function BomPartsImportPage() {
  const paste = usePartsPaste(PART_FIELDS)
  const [division, setDivision] = useState('')
  const [sourceRef, setSourceRef] = useState('')
  const [choices, setChoices] = useState<Record<string, Choice>>({})
  const [result, setResult] = useState<{ key: string; data: BomPartImport } | null>(null)
  // **고른 재질도 목록에 남긴다** — 고르고 다시 미리보기하면 그 재질은 「새로」 가 되어 고를
  // 목록에서 빠지는데, 그러면 잘못 고른 것을 되돌릴 자리가 없다. 붙여넣은 줄이 같은 동안만.
  const [asked, setAsked] = useState<{ rows: string; list: Ask[] }>({ rows: '', list: [] })
  const [done, setDone] = useState<BomPartImport | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const rows: BomPartRowIn[] = useMemo(
    () =>
      paste.records.map((one) => ({
        material: one.material ?? null,
        part: one.part ?? null,
        product: one.product ?? null,
        part_code: one.part_code ?? null,
        division: one.division ?? null,
      })),
    [paste.records]
  )
  const hasMaterial = paste.columns.includes('material')
  const body = {
    rows,
    division: division.trim() || null,
    source_ref: sourceRef.trim() || null,
    choices: Object.fromEntries(Object.entries(choices).map(([text, one]) => [text, one.id])),
  }
  const key = JSON.stringify(body)
  // **고른 것 · 붙여넣은 것이 바뀌면 미리보기는 낡는다** — 낡은 미리보기로 넣으면 본 것과 다른
  // 재료에 줄이 들어간다.
  const fresh = result !== null && result.key === key ? result.data : null
  const shown = result?.data ?? null
  const rowsKey = JSON.stringify(rows)
  const asks = asked.rows === rowsKey ? asked.list : []

  async function run(dryRun: boolean) {
    setBusy(true)
    setError(null)
    try {
      const data = await materialsApi.importBomParts({ ...body, dry_run: dryRun })
      if (dryRun) {
        setResult({ key, data })
        setDone(null)
        setAsked({ rows: rowsKey, list: merge(asks, pending(data)) })
      } else {
        setDone(data)
        setResult(null)
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('가져오지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const ordered = shown
    ? [...shown.rows].sort((a, b) => Number(a.status === 'new') - Number(b.status === 'new'))
    : []

  return (
    <div className="space-y-4">
      <PageHeader
        title="BOM 적용 부품 가져오기"
        description="부품표를 붙여넣으면 재질 칸으로 재료를 찾아 재료마다 적용 부품 줄(파트명 · 제품 · 부품코드 · 사업부)을 넣습니다. 못 찾은 재질은 직접 고릅니다."
        actions={
          <Button variant="ghost" asChild>
            <Link to="/materials">재료 목록</Link>
          </Button>
        }
      />

      <PartsPasteFields
        paste={paste}
        fields={PART_FIELDS}
        placeholder={'품번\t품명\t재질\t모델\n100-A\t도어 이너\tSECC\t냉장고 A'}
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:max-w-3xl">
        <div className="space-y-1.5">
          <Label htmlFor="bom-division">사업부(칸이 빈 줄에)</Label>
          <Input
            id="bom-division"
            placeholder="예: 가전"
            value={division}
            onChange={(event) => setDivision(event.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="bom-ref">출처(어느 BOM)</Label>
          <Input
            id="bom-ref"
            placeholder="예: 냉장고 A BOM 2026-10"
            value={sourceRef}
            onChange={(event) => setSourceRef(event.target.value)}
          />
        </div>
      </div>

      {rows.length > 0 && !hasMaterial && (
        <p className="text-sm text-amber-700 dark:text-amber-400">
          재질 열을 골라야 재료를 찾습니다.
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          disabled={busy || rows.length === 0 || !hasMaterial}
          onClick={() => void run(true)}
        >
          미리보기
        </Button>
        <Button
          disabled={busy || !fresh || (fresh.counts.new ?? 0) === 0}
          onClick={() => void run(false)}
        >
          {fresh ? `${fresh.counts.new ?? 0}줄 넣기` : '넣기'}
        </Button>
        {shown && !fresh && (
          <span className="text-muted-foreground self-center text-sm">
            바뀐 것이 있습니다 — 다시 미리보기를 누릅니다.
          </span>
        )}
      </div>

      <ErrorNotice error={error} />

      {done && (
        <div className="space-y-2 rounded-md border p-3 text-sm">
          <p className="font-medium">
            재료 {done.materials.length}개에{' '}
            {done.materials.reduce((sum, one) => sum + one.new, 0)}줄을 넣었습니다.
          </p>
          <ul className="flex flex-wrap gap-2">
            {done.materials.map((one) => (
              <li key={one.id}>
                <Link className="underline" to={`/materials/${one.id}?tab=parts`}>
                  <RecordName name={one.name} />
                </Link>{' '}
                <span className="text-muted-foreground">+{one.new}</span>
              </li>
            ))}
          </ul>
          <Counts counts={done.counts} />
        </div>
      )}

      {shown && (
        <div className="space-y-3">
          <Counts counts={shown.counts} />

          {asks.length > 0 && (
            <div className="space-y-2 rounded-md border p-3">
              <p className="text-sm font-medium">재질 짝 고르기</p>
              <p className="text-muted-foreground text-xs">
                재료 이름 · 별칭 · Grade 로 하나를 못 찾은 재질입니다. 고르고 다시 미리보기를
                누릅니다 — 고르지 않은 재질의 줄은 넣지 않습니다.
              </p>
              <div className="rounded-md border">
                <Table className="text-sm">
                  <TableHeader>
                    <TableRow>
                      <TableHead>재질</TableHead>
                      <TableHead>줄</TableHead>
                      <TableHead>판정</TableHead>
                      <TableHead>재료</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {asks.map((one) => (
                      <TableRow key={one.material}>
                        <TableCell className="font-medium">{one.material}</TableCell>
                        <TableCell className="tabular-nums">{one.count}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{BOM_STATUS_LABELS[one.status]}</Badge>
                        </TableCell>
                        <TableCell>
                          <ChoiceField
                            ask={one}
                            value={choices[one.material] ?? null}
                            onChange={(next) =>
                              setChoices((current) => {
                                const copy = { ...current }
                                if (next) copy[one.material] = next
                                else delete copy[one.material]
                                return copy
                              })
                            }
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}

          {shown.materials.length > 0 && (
            <p className="text-sm">
              들어갈 재료:{' '}
              {shown.materials.map((one, index) => (
                <span key={one.id}>
                  {index > 0 && ' · '}
                  <RecordName name={one.name} /> {one.new}줄
                </span>
              ))}
            </p>
          )}

          <div className="rounded-md border">
            <Table className="text-xs">
              <TableHeader>
                <TableRow>
                  <TableHead>줄</TableHead>
                  <TableHead>판정</TableHead>
                  <TableHead>재질</TableHead>
                  <TableHead>재료</TableHead>
                  <TableHead>파트명</TableHead>
                  <TableHead>제품</TableHead>
                  <TableHead>부품코드</TableHead>
                  <TableHead>사업부</TableHead>
                  <TableHead>이유</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ordered.slice(0, SHOWN).map((row) => (
                  <TableRow key={row.index}>
                    <TableCell className="tabular-nums">{row.index + 1}</TableCell>
                    <TableCell>
                      <Badge variant={row.status === 'new' ? 'default' : 'outline'}>
                        {BOM_STATUS_LABELS[row.status] ?? row.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{row.material}</TableCell>
                    <TableCell>
                      {row.material_name ? <RecordName name={row.material_name} /> : <None />}
                    </TableCell>
                    <TableCell>{row.part ?? <None />}</TableCell>
                    <TableCell>{row.product ?? <None />}</TableCell>
                    <TableCell className="font-mono">{row.part_code ?? <None />}</TableCell>
                    <TableCell>{row.division ?? <None />}</TableCell>
                    <TableCell>{row.reason ?? <None />}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {ordered.length > SHOWN && (
            <p className="text-muted-foreground text-xs">
              {SHOWN}줄까지 보입니다(전체 {ordered.length.toLocaleString('ko-KR')}줄) — 못 넣는
              줄이 먼저 섭니다.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function None() {
  return <span className="text-muted-foreground">—</span>
}

function Counts({ counts }: { counts: Record<string, number> }) {
  return (
    <div className="flex flex-wrap gap-2 text-sm">
      {Object.entries(BOM_STATUS_LABELS).map(([status, label]) =>
        counts[status] ? (
          <Badge key={status} variant={status === 'new' ? 'default' : 'outline'}>
            {label} {counts[status]}
          </Badge>
        ) : null
      )}
    </div>
  )
}

/** 여럿에 맞았으면 그 후보에서, 못 찾았으면 재료를 찾아서 고른다. */
function ChoiceField({
  ask,
  value,
  onChange,
}: {
  ask: Ask
  value: Choice | null
  onChange: (next: Choice | null) => void
}) {
  if (ask.status === 'ambiguous' && ask.candidates.length > 0) {
    return (
      <select
        aria-label={`${ask.material} 재료`}
        className="border-input bg-background h-8 rounded-md border px-2 text-sm"
        value={value?.id ?? ''}
        onChange={(event) => {
          const found = ask.candidates.find((one) => one.id === event.target.value)
          onChange(found ?? null)
        }}
      >
        <option value="">(고르지 않음)</option>
        {ask.candidates.map((one) => (
          <option key={one.id} value={one.id}>
            {one.name}
          </option>
        ))}
      </select>
    )
  }
  return (
    <MaterialPicker
      ariaLabel={`${ask.material} 재료`}
      // 피커는 고른 것의 이름만 그린다 — 고른 재료 전체를 들고 다니지 않는다.
      value={value ? ({ id: value.id, record_name: value.name } as Material) : null}
      onSelect={(material) => onChange({ id: material.id, name: material.record_name })}
      placeholder="재료 찾기"
    />
  )
}
