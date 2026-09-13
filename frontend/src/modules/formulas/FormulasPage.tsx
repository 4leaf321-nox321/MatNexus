/**
 * 계산식 — **파이썬 폴더 없이, 배포 없이 식 하나를 붙인다** (ADR 0030).
 *
 * 식 하나가 붙을 자리는 셋이다. 어디에 걸리는지가 곧 「자리」 다:
 *
 *   적합식    재료 상세 → 물성 카드 → 적합식 목록. `y = f(x; 계수들)` 을 곡선에 맞춘다.
 *   값 단계   처리 레시피 → 단계. 앞 단계의 값(항복강도·인장강도…)으로 값 하나를 낸다.
 *   열 단계   처리 레시피 → 단계. 프레임의 열(진응력…)로 열 하나를 더한다.
 *
 * 정렬·구간 탐색·회귀·교점 같은 **알고리즘은 여기서 못 만든다** — 그것은 확장
 * 폴더(`backend/extensions/`)의 일이다. 여기는 「한 줄로 적히는 식」 까지다.
 *
 * ## 저장하기 전에 돌려 본다 (D6)
 *
 * 문법이 맞는데 뜻이 틀린 식(축을 바꿔 적음, 단위가 천 배)은 저장해도 오류가 안 난다.
 * 채택된 처리 결과 하나를 골라 미리보기로 돌리면 계수·값·앞 몇 점이 나온다.
 *
 * ## 고치면 판이 오르고, 쓰이는 식은 못 지운다 (D4)
 *
 * 식을 고쳐도 이미 저장된 레시피·결과·카드는 옛 판을 든 채 그대로다. 레시피가 쓰는
 * 식은 지우지 못하고 **끈다** — 옛 결과는 그대로 읽힌다.
 */

import { Loader2, Pencil, Play, Plus, Power, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { KINDS, formulasApi } from '@/modules/formulas/api'
import type {
  Formula,
  FormulaKind,
  FormulaParameter,
  FormulaPreview,
  FormulaSpec,
  FormulaVariable,
  FormulaVocabulary,
} from '@/modules/formulas/api'
import { testsApi } from '@/modules/tests/api'
import type { TestRun } from '@/modules/tests/api'
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
import { useResource } from '@/shared/hooks/useResource'
import { SI_BY_DIMENSION } from '@/shared/units'

const SELECT = 'border-input bg-background h-9 w-full rounded-md border px-2 text-sm'
const REFERENCE_LABELS: Record<string, string> = { recipes: '레시피', results: '결과', cards: '카드' }
const SI_UNITS = Array.from(new Set(Object.values(SI_BY_DIMENSION))).sort()

/**
 * 새 식의 첫 모양 — **예시가 채워진 채로.** 빈 칸 여덟 개를 앞에 두면 사람은 무엇을 적어야
 * 하는지부터 물었다(2026-09-13). 지워 쓰는 편이 빠르고, 예시가 곧 설명이다. 키는 비워 둔다 —
 * 예시 키를 그대로 저장하면 다음 사람이 같은 키에 부딪힌다.
 */
function emptySpec(kind: FormulaKind): FormulaSpec {
  if (kind === 'family') {
    return {
      key: '',
      kind,
      label: 'Swift (예)',
      expression: 'K * pow(e0 + x, n)',
      describe: null,
      variables: [{ name: 'x', unit: '1', label: null }],
      parameters: [
        { name: 'K', unit: 'Pa', initial: 5e8, lower: 0, upper: 5e9 },
        { name: 'e0', unit: '1', initial: 0.01, lower: 1e-6, upper: 1 },
        { name: 'n', unit: '1', initial: 0.2, lower: 0, upper: 1 },
      ],
      result: null,
      x_column: 'strain_true_plastic',
      y_column: 'stress_true',
      block: 'hardening',
      applies_to: ['Metal'],
    }
  }
  if (kind === 'scalar_step') {
    return {
      key: '',
      kind,
      label: '항복비 (예)',
      expression: 'proof_stress / tensile_strength',
      describe: null,
      variables: [
        { name: 'proof_stress', unit: 'Pa', label: null },
        { name: 'tensile_strength', unit: 'Pa', label: null },
      ],
      parameters: [],
      result: { key: 'yield_ratio', label: '항복비', si_unit: '1' },
      x_column: null,
      y_column: null,
      block: null,
      applies_to: ['tensile'],
    }
  }
  return {
    key: '',
    kind,
    label: '진응력 MPa (예)',
    expression: 'stress_true * 1e-6',
    describe: null,
    variables: [{ name: 'stress_true', unit: 'Pa', label: null }],
    parameters: [],
    result: { key: 'stress_true_mpa', label: '진응력 (MPa)', si_unit: '1' },
    x_column: null,
    y_column: null,
    block: null,
    applies_to: [],
  }
}

function specOf(row: Formula): FormulaSpec {
  return {
    key: row.key,
    kind: row.kind,
    label: row.label,
    expression: row.expression,
    describe: row.describe,
    variables: row.variables.map((one) => ({
      name: String(one['name'] ?? ''),
      unit: String(one['unit'] ?? '1'),
      label: (one['label'] as string | null) ?? null,
    })),
    parameters: row.parameters.map((one) => ({
      name: String(one['name'] ?? ''),
      unit: String(one['unit'] ?? '1'),
      initial: Number(one['initial'] ?? 1),
      lower: one['lower'] == null ? null : Number(one['lower']),
      upper: one['upper'] == null ? null : Number(one['upper']),
    })),
    result: row.result
      ? {
          key: String(row.result['key'] ?? ''),
          label: String(row.result['label'] ?? ''),
          si_unit: String(row.result['si_unit'] ?? '1'),
        }
      : null,
    x_column: row.x_column,
    y_column: row.y_column,
    block: row.block,
    applies_to: row.applies_to,
  }
}

function referencesText(row: Formula): string {
  const parts = Object.entries(row.references ?? {})
    .filter(([, count]) => count > 0)
    .map(([key, count]) => `${REFERENCE_LABELS[key] ?? key} ${count}`)
  return parts.length > 0 ? parts.join(' · ') : '없음'
}

function isReferenced(row: Formula): boolean {
  return Object.values(row.references ?? {}).some((count) => count > 0)
}

export default function FormulasPage() {
  const rows = useResource(() => formulasApi.list(), [])
  const vocabulary = useResource(() => formulasApi.vocabulary(), [])
  const [editing, setEditing] = useState<{ row: Formula | null; kind: FormulaKind } | null>(null)
  const [removing, setRemoving] = useState<Formula | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function toggle(row: Formula) {
    setBusy(true)
    setError(null)
    try {
      await formulasApi.update(row.id, { enabled: !row.enabled })
      setNotice(row.enabled ? `${row.label} 비활성화 — 목록에서 제외.` : `${row.label} 활성화.`)
      rows.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('바꾸지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!removing) return
    setBusy(true)
    setError(null)
    try {
      await formulasApi.remove(removing.id)
      setNotice(`${removing.label} 삭제 완료.`)
      setRemoving(null)
      rows.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="계산식"
        description="식 한 줄 → 처리 단계 또는 카드의 식. 개발자·배포 없이."
      />

      {/* **무엇을 만들까요 — 셋 중 하나를 고른다.** 단추 이름(적합식·값 단계·열 단계)만으로는
          무엇이 나오는지 안 보였다. 카드마다 용도·어디에 뜨나·변수는 어디서 오나·예를 적는다. */}
      <section className="space-y-2">
        <h2 className="text-sm font-medium">무엇을 만들까요?</h2>
        <div className="grid gap-3 md:grid-cols-3">
          {KINDS.map((kind) => (
            <button
              key={kind.key}
              type="button"
              className="hover:bg-muted/50 flex flex-col gap-1.5 rounded-md border p-3 text-left"
              onClick={() => setEditing({ row: null, kind: kind.key })}
            >
              <span className="flex items-center gap-1 font-medium">
                <Plus className="h-4 w-4" />
                {kind.label}
              </span>
              <span className="text-sm">{kind.purpose}</span>
              <span className="text-muted-foreground text-xs">
                <b className="text-foreground">어디에</b> {kind.where}
              </span>
              <span className="text-muted-foreground text-xs">
                <b className="text-foreground">변수는</b> {kind.inputs}
              </span>
              <code className="bg-muted mt-1 rounded px-1.5 py-0.5 text-xs">{kind.example}</code>
            </button>
          ))}
        </div>
        <p className="text-muted-foreground text-xs">
          범위: 한 줄로 적히는 식까지. 정렬·구간 탐색·회귀·교점처럼{' '}
          <b className="text-foreground">순서와 조건이 있는 계산</b>은 확장 폴더(개발자)의 일.
        </p>
      </section>

      <ErrorNotice error={error ?? rows.error} />
      {notice && <div className="rounded-md border p-3 text-sm">{notice}</div>}

      <div className="overflow-x-auto rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>자리</TableHead>
            <TableHead>이름</TableHead>
            <TableHead>식</TableHead>
            <TableHead>키</TableHead>
            <TableHead>판</TableHead>
            <TableHead>쓰는 곳</TableHead>
            <TableHead>상태</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.data?.length === 0 && (
            <TableRow>
              <TableCell colSpan={8} className="text-muted-foreground">
                계산식 없음 — 위 카드에서 생성.
              </TableCell>
            </TableRow>
          )}
          {rows.data?.map((row) => (
            <TableRow key={row.id}>
              <TableCell>
                <Badge variant="outline">{row.kind_label}</Badge>
              </TableCell>
              <TableCell>{row.label}</TableCell>
              <TableCell>
                <code>{row.expression}</code>
              </TableCell>
              <TableCell>
                <code>{row.registry_key}</code>
              </TableCell>
              <TableCell>v{row.version}</TableCell>
              <TableCell>{referencesText(row)}</TableCell>
              <TableCell>
                {row.enabled ? <Badge>켜짐</Badge> : <Badge variant="secondary">꺼짐</Badge>}
              </TableCell>
              <TableCell>
                <div className="flex justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    title="편집"
                    onClick={() => setEditing({ row, kind: row.kind as FormulaKind })}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    title={row.enabled ? '비활성화 — 목록에서 빠지되 옛 결과는 그대로' : '활성화'}
                    disabled={busy}
                    onClick={() => void toggle(row)}
                  >
                    <Power className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    title={isReferenced(row) ? '삭제 불가 (쓰는 곳 있음) — 비활성화로 대체' : '삭제'}
                    disabled={busy || isReferenced(row)}
                    onClick={() => setRemoving(row)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      </div>

      {editing && (
        <FormulaDialog
          row={editing.row}
          kind={editing.kind}
          vocabulary={vocabulary.data}
          onClose={() => setEditing(null)}
          onDone={(message) => {
            setEditing(null)
            setNotice(message)
            rows.reload()
          }}
        />
      )}

      <ConfirmDialog
        open={removing !== null}
        title="계산식 삭제"
        body={
          removing ? (
            <>
              <code>{removing.registry_key}</code> ({removing.label}) 삭제. 쓰는 곳 없음 — 되돌릴 것도
              없음.
            </>
          ) : null
        }
        busy={busy}
        onConfirm={() => void remove()}
        onClose={() => setRemoving(null)}
      />
    </div>
  )
}

// ── 편집 ────────────────────────────────────────────────────────────────────

function FormulaDialog({
  row,
  kind,
  vocabulary,
  onClose,
  onDone,
}: {
  row: Formula | null
  kind: FormulaKind
  vocabulary: FormulaVocabulary | null
  onClose: () => void
  onDone: (message: string) => void
}) {
  const [spec, setSpec] = useState<FormulaSpec>(() => (row ? specOf(row) : emptySpec(kind)))
  const [appliesText, setAppliesText] = useState(() =>
    (row ? row.applies_to : emptySpec(kind).applies_to).join(', ')
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // 미리보기 — 채택된 시험을 이름으로 찾아 고른다.
  const [query, setQuery] = useState('')
  const [runs, setRuns] = useState<TestRun[]>([])
  const [picked, setPicked] = useState<TestRun | null>(null)
  const [preview, setPreview] = useState<FormulaPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)

  const kindMeta = KINDS.find((one) => one.key === kind) ?? KINDS[0]
  const isFamily = kind === 'family'
  const names = useMemo(() => {
    const source = isFamily || kind === 'column_step' ? vocabulary?.columns : vocabulary?.scalars
    return source ?? []
  }, [vocabulary, kind, isFamily])

  useEffect(() => {
    const needle = query.trim()
    if (needle.length < 1) {
      setRuns([])
      return
    }
    let alive = true
    const timer = setTimeout(() => {
      testsApi
        .runs({ adopted: true, q: needle, limit: 12 })
        .then((page) => {
          if (alive) setRuns(page.items)
        })
        .catch(() => {
          if (alive) setRuns([])
        })
    }, 200)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [query])

  const payload = useMemo<FormulaSpec>(
    () => ({
      ...spec,
      applies_to: appliesText
        .split(',')
        .map((one) => one.trim())
        .filter(Boolean),
    }),
    [spec, appliesText],
  )
  const ready =
    payload.key.trim().length >= 2 &&
    payload.label.trim() !== '' &&
    payload.expression.trim() !== '' &&
    payload.variables.every((one) => one.name.trim() !== '') &&
    (isFamily ? payload.parameters.length > 0 : Boolean(payload.result?.key.trim()))

  function setVariable(index: number, patch: Partial<FormulaVariable>) {
    setSpec((prev) => ({
      ...prev,
      variables: prev.variables.map((one, at) => (at === index ? { ...one, ...patch } : one)),
    }))
  }
  function setParameter(index: number, patch: Partial<FormulaParameter>) {
    setSpec((prev) => ({
      ...prev,
      parameters: prev.parameters.map((one, at) => (at === index ? { ...one, ...patch } : one)),
    }))
  }

  async function runPreview() {
    if (!picked?.adopted_result_id) return
    setPreviewing(true)
    setError(null)
    try {
      setPreview(await formulasApi.preview(payload, picked.adopted_result_id))
    } catch (caught) {
      setPreview(null)
      setError(caught instanceof Error ? caught : new Error('미리보기를 돌리지 못했습니다.'))
    } finally {
      setPreviewing(false)
    }
  }

  async function submit() {
    setSaving(true)
    setError(null)
    try {
      if (row) {
        const { key: _key, kind: _kind, ...rest } = payload
        const saved = await formulasApi.update(row.id, rest)
        onDone(
          saved.version > row.version
            ? `${saved.label} 편집 완료 — v${saved.version}. 저장된 결과는 옛 판 그대로.`
            : `${saved.label} 편집 완료.`,
        )
      } else {
        const saved = await formulasApi.create(payload)
        onDone(`${saved.label} 생성 완료 — ${kindMeta.where} 에 바로 표시.`)
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {row ? '계산식 편집' : `${kindMeta.label} 생성`}
            {row && (
              <span className="text-muted-foreground ml-2 text-sm font-normal">
                {row.registry_key} · v{row.version}
              </span>
            )}
          </DialogTitle>
          <DialogDescription>
            {kindMeta.purpose}
            {row && ' 식·변수·계수 변경 시 판이 오름 — 저장된 결과는 옛 판 그대로.'}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3">
          {/* **어디에 뜨고 변수는 어디서 오나** — 창 안에서도 한 번 더. 첫 화면을 안 거치고
              「편집」 으로 들어오는 사람이 있다. */}
          <div className="bg-muted/40 grid gap-1 rounded-md p-3 text-xs md:grid-cols-2">
            <div>
              <b>어디에 뜨나</b> — {kindMeta.where}
            </div>
            <div>
              <b>변수는 어디서</b> — {kindMeta.inputs}
            </div>
            {!row && (
              <div className="text-muted-foreground md:col-span-2">
                예시 채워짐 — 키 입력 후 식·이름을 지워 쓰기. 저장 전 아래 「미리보기」 로 실제
                시험에 적용해 값 확인.
              </div>
            )}
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="formula-key">키</Label>
              <Input
                id="formula-key"
                value={spec.key}
                disabled={row !== null}
                placeholder="예: yield_ratio (영문 snake_case)"
                onChange={(event) => setSpec({ ...spec, key: event.target.value })}
              />
              <p className="text-muted-foreground text-xs">
                등록 키 <code>formula.{spec.key || '…'}</code> — 저장 후 변경 불가.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="formula-label">이름</Label>
              <Input
                id="formula-label"
                value={spec.label}
                placeholder="예: 항복비"
                onChange={(event) => setSpec({ ...spec, label: event.target.value })}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="formula-expression">식</Label>
            <Textarea
              id="formula-expression"
              rows={2}
              value={spec.expression}
              placeholder={isFamily ? '예: K * pow(e0 + x, n)' : '예: proof_stress / tensile_strength'}
              onChange={(event) => setSpec({ ...spec, expression: event.target.value })}
            />
            <p className="text-muted-foreground text-xs">
              함수: {vocabulary?.functions.join(' ') ?? '…'} · 상수:{' '}
              {vocabulary?.constants.join(' ') ?? '…'}. 식의 이름은 전부 아래{' '}
              {isFamily ? '변수·계수' : '입력'}에 선언 — 미선언 이름은 저장 불가.
            </p>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>
                {isFamily
                  ? '변수 — x = 아래 「x 열」 의 값'
                  : kind === 'scalar_step'
                    ? '입력 — 앞 단계의 값 (출처 단계 표시)'
                    : '입력 — 곡선의 열 (원본 파일 채널 또는 앞 단계의 열)'}
              </Label>
              {!isFamily && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    setSpec({ ...spec, variables: [...spec.variables, { name: '', unit: '1', label: null }] })
                  }
                >
                  <Plus className="h-4 w-4" />
                </Button>
              )}
            </div>
            <datalist id="formula-names">
              {names.map((one) => (
                <option key={one['key']} value={one['key']}>
                  {one['label']}
                </option>
              ))}
            </datalist>
            <datalist id="formula-units">
              {SI_UNITS.map((one) => (
                <option key={one} value={one} />
              ))}
            </datalist>
            {spec.variables.map((one, index) => (
              <div key={index} className="grid grid-cols-[1fr_8rem_auto] gap-2">
                {isFamily ? (
                  <Input value={one.name} placeholder="이름" disabled />
                ) : (
                  // **목록에서 고른다.** 이름을 손으로 치면 오타가 저장되고, 그 식은 돌 때마다
                  // 「값이 없습니다」 만 남긴다. 어느 단계가 내는지가 옆에 붙어 「어디서 오나」 에
                  // 답한다. 목록에 없는 이름(확장이 나중에 낼 것)은 「직접 입력」 으로.
                  <select
                    className={SELECT}
                    aria-label={`${index + 1}번 입력`}
                    value={names.some((n) => n['key'] === one.name) ? one.name : one.name ? '__custom__' : ''}
                    onChange={(event) => {
                      const next = event.target.value
                      if (next === '__custom__') {
                        setVariable(index, { name: one.name || 'x' })
                        return
                      }
                      const found = names.find((n) => n['key'] === next)
                      const unit = found?.['label']?.match(/\(([^)]*)\)\s*$/)?.[1]
                      setVariable(index, { name: next, ...(unit && unit !== '?' ? { unit } : {}) })
                    }}
                  >
                    <option value="">— 선택 —</option>
                    {names.map((n) => (
                      <option key={n['key']} value={n['key']}>
                        {n['key']} · {n['label']}
                        {n['made_by'] ? ` ← ${n['made_by']}` : ''}
                      </option>
                    ))}
                    <option value="__custom__">직접 입력…</option>
                  </select>
                )}
                {!isFamily && !names.some((n) => n['key'] === one.name) && one.name !== '' && (
                  <Input
                    className="col-span-3"
                    value={one.name}
                    placeholder="이름 (영문 snake_case)"
                    onChange={(event) => setVariable(index, { name: event.target.value })}
                  />
                )}
                <Input
                  list="formula-units"
                  value={one.unit ?? '1'}
                  placeholder="단위(SI)"
                  onChange={(event) => setVariable(index, { unit: event.target.value })}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={isFamily || spec.variables.length <= 1}
                  onClick={() =>
                    setSpec({ ...spec, variables: spec.variables.filter((_, at) => at !== index) })
                  }
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>

          {isFamily ? (
            <>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label>계수 — 산출 대상. 초기값·경계는 결과에 기록</Label>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setSpec({
                        ...spec,
                        parameters: [...spec.parameters, { name: '', unit: '1', initial: 1, lower: null, upper: null }],
                      })
                    }
                  >
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>
                <div className="text-muted-foreground grid grid-cols-[1fr_6rem_6rem_6rem_6rem_auto] gap-2 text-xs">
                  <span>이름</span>
                  <span>단위</span>
                  <span>초기값</span>
                  <span>아래</span>
                  <span>위</span>
                  <span />
                </div>
                {spec.parameters.map((one, index) => (
                  <div key={index} className="grid grid-cols-[1fr_6rem_6rem_6rem_6rem_auto] gap-2">
                    <Input value={one.name} onChange={(event) => setParameter(index, { name: event.target.value })} />
                    <Input
                      list="formula-units"
                      value={one.unit ?? '1'}
                      onChange={(event) => setParameter(index, { unit: event.target.value })}
                    />
                    <Input
                      value={String(one.initial ?? '')}
                      onChange={(event) => setParameter(index, { initial: Number(event.target.value) })}
                    />
                    <Input
                      value={one.lower == null ? '' : String(one.lower)}
                      placeholder="-∞"
                      onChange={(event) =>
                        setParameter(index, { lower: event.target.value === '' ? null : Number(event.target.value) })
                      }
                    />
                    <Input
                      value={one.upper == null ? '' : String(one.upper)}
                      placeholder="+∞"
                      onChange={(event) =>
                        setParameter(index, { upper: event.target.value === '' ? null : Number(event.target.value) })
                      }
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={spec.parameters.length <= 1}
                      onClick={() =>
                        setSpec({ ...spec, parameters: spec.parameters.filter((_, at) => at !== index) })
                      }
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                <div className="space-y-1.5">
                  <Label>x 열</Label>
                  <Input
                    list="formula-names"
                    value={spec.x_column ?? ''}
                    onChange={(event) => setSpec({ ...spec, x_column: event.target.value })}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>y 열</Label>
                  <Input
                    list="formula-names"
                    value={spec.y_column ?? ''}
                    onChange={(event) => setSpec({ ...spec, y_column: event.target.value })}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>블록</Label>
                  <select
                    className={SELECT}
                    value={spec.block ?? 'hardening'}
                    onChange={(event) => setSpec({ ...spec, block: event.target.value })}
                  >
                    {(vocabulary?.blocks ?? [{ key: 'hardening', label: '경화' }]).map((one) => (
                      <option key={one['key']} value={one['key']}>
                        {one['label']} ({one['key']})
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </>
          ) : (
            <div className="grid gap-3 md:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="formula-result-key">내는 {kind === 'scalar_step' ? '값' : '열'}의 키</Label>
                <Input
                  id="formula-result-key"
                  value={spec.result?.key ?? ''}
                  placeholder="예: yield_ratio"
                  onChange={(event) =>
                    setSpec({ ...spec, result: { ...(spec.result ?? { label: '', si_unit: '1' }), key: event.target.value } })
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="formula-result-label">내는 {kind === 'scalar_step' ? '값' : '열'}의 이름</Label>
                <Input
                  id="formula-result-label"
                  value={spec.result?.label ?? ''}
                  placeholder="예: 항복비"
                  onChange={(event) =>
                    setSpec({ ...spec, result: { ...(spec.result ?? { key: '', si_unit: '1' }), label: event.target.value } })
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="formula-result-unit">단위(SI)</Label>
                <Input
                  id="formula-result-unit"
                  list="formula-units"
                  value={spec.result?.si_unit ?? '1'}
                  onChange={(event) =>
                    setSpec({ ...spec, result: { ...(spec.result ?? { key: '', label: '' }), si_unit: event.target.value } })
                  }
                />
              </div>
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="formula-applies">{isFamily ? '재료군' : '시험 종류'} (공란 = 제한 없음)</Label>
              <Input
                id="formula-applies"
                value={appliesText}
                placeholder={isFamily ? '예: Metal' : '예: tensile'}
                onChange={(event) => setAppliesText(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="formula-describe">설명</Label>
              <Input
                id="formula-describe"
                value={spec.describe ?? ''}
                placeholder="카드·레시피에 실릴 한 줄"
                onChange={(event) => setSpec({ ...spec, describe: event.target.value || null })}
              />
            </div>
          </div>

          {/* 미리보기 — 저장 전에 실제 결과로 돌려 본다. 아무것도 남기지 않는다. */}
          <div className="space-y-2 rounded-md border p-3">
            <Label>저장 전 미리보기 — 채택된 시험 선택</Label>
            {picked ? (
              <div className="flex items-center justify-between gap-2 text-sm">
                <span>
                  {picked.record_name}
                  <span className="text-muted-foreground"> · {picked.material_name ?? ''} · {picked.test_type_label}</span>
                </span>
                <Button variant="ghost" size="sm" onClick={() => setPicked(null)}>
                  다른 시험
                </Button>
              </div>
            ) : (
              <>
                <Input
                  value={query}
                  placeholder="시험 이름·재료로 검색"
                  onChange={(event) => setQuery(event.target.value)}
                />
                {runs.length > 0 && (
                  <ul className="max-h-40 overflow-y-auto rounded-md border text-sm">
                    {runs
                      .filter((one) => one.adopted_result_id)
                      .map((one) => (
                        <li key={one.id}>
                          <button
                            type="button"
                            className="hover:bg-muted w-full px-2 py-1 text-left"
                            onClick={() => {
                              setPicked(one)
                              setQuery('')
                              setRuns([])
                            }}
                          >
                            {one.record_name}
                            <span className="text-muted-foreground"> · {one.material_name ?? ''} · {one.test_type_label}</span>
                          </button>
                        </li>
                      ))}
                  </ul>
                )}
              </>
            )}
            <Button variant="outline" size="sm" disabled={!picked || !ready || previewing} onClick={() => void runPreview()}>
              {previewing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Play className="mr-1 h-4 w-4" />}
              미리보기
            </Button>
            {preview && <PreviewResult preview={preview} />}
          </div>

          <ErrorNotice error={error} />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
          <Button disabled={!ready || saving} onClick={() => void submit()}>
            {saving && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            {row ? '편집' : '생성'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function PreviewResult({ preview }: { preview: FormulaPreview }) {
  const parameters = preview.parameters ?? []
  const sample = preview.sample ?? []
  const notes = preview.notes ?? []
  return (
    <div className={`rounded-md border p-2 text-sm ${preview.ok ? '' : 'border-destructive/40 text-destructive'}`}>
      <div>{preview.message}</div>
      {parameters.length > 0 && (
        <ul className="mt-1 grid grid-cols-3 gap-1">
          {parameters.map((one) => (
            <li key={String(one['name'])}>
              <code>
                {String(one['name'])} = {Number(one['value']).toPrecision(4)} {String(one['unit'] ?? '')}
              </code>
            </li>
          ))}
        </ul>
      )}
      {sample.length > 0 && (
        <div className="mt-1 overflow-x-auto">
          <table className="text-xs">
            <thead>
              <tr>
                {Object.keys(sample[0]).map((key) => (
                  <th key={key} className="pr-3 text-left font-medium">
                    {key}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sample.map((point, index) => (
                <tr key={index}>
                  {Object.values(point).map((value, at) => (
                    <td key={at} className="pr-3">
                      {Number(value).toPrecision(5)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {notes.length > 0 && <div className="text-muted-foreground mt-1">{notes.join(' ')}</div>}
    </div>
  )
}
