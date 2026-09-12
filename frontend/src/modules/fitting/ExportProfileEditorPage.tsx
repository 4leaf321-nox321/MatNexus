/**
 * 해석용 물성 정의 편집기 — **물성 묶음으로 쌓고, 옆에서 실제 덱을 본다.**
 *
 * 정의는 JSON 줄 목록이지만 줄로 적게 하지 않는다. 솔버 덱은 「키워드 한 줄 + 그
 * 아래 값·표 줄」 의 반복이라, 그 단위(묶음)로 보이면 「탄성 · 밀도 · 소성」 이 된다
 * (2026-09-05, 줄을 평면으로 쌓게 하니 덱 문법과 카드 값 이름을 동시에 알아야 했다).
 * 저장 형식은 그대로 줄이다(`deckSections`) — 옛 정의도 그대로 열린다.
 *
 * ## 세 출발점
 *
 *   물성 묶음 추가      블록 하나로 키워드·값·표 초안 — 값 이름을 적지 않는다
 *   예제 덱에서 시작    그 솔버의 덱을 올리면 줄·칸 폭을 읽는다(ADR 0006 과 같은 선)
 *   빈 묶음             키워드부터 손으로
 *
 * ## 미리보기가 절반이다
 *
 * 오른쪽은 **실제 카드 하나로 지금 정의를 그려 본 것**이다. 묶음에 마우스를 올리면 그
 * 묶음이 만든 줄이 강조된다 — 「어느 정의가 어느 줄이 됐나」 를 눈으로 잇는다. 틀린
 * 덱은 솔버가 오류로 알려 주지 않는다: 칸이 어긋나면 다른 필드로 읽히고 해석은 그대로
 * 돌아 그럴듯한 결과를 낸다.
 *
 * **못 냈어도 오류를 던지지 않는다.** 못 낸 이유가 응답 안에 있고, 그것을 보여 주는
 * 것이 미리보기의 일이다.
 */

import { useEffect, useMemo, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronRight,
  Layers,
  Plus,
  Search,
  Trash2,
  Upload,
} from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { CardPickerDialog } from '@/modules/fitting/CardPickerDialog'
import { DeckKeyPicker } from '@/modules/fitting/DeckKeyPicker'
import { fittingApi } from '@/modules/fitting/api'
import type {
  BlockSpec,
  DeckKeys,
  DeckPreview,
  ExportProfile,
  PropertyCard,
} from '@/modules/fitting/api'
import { blank, BLOCKS, fieldLabel, FORMATS, fromDefinitionLine, fromScan, toDefinitionLine } from '@/modules/fitting/deckLines'
import type { DeckLine, FieldSpec, LineKind } from '@/modules/fitting/deckLines'
import { fromSections, lineRanges, summarize, toSections } from '@/modules/fitting/deckSections'
import type { Section } from '@/modules/fitting/deckSections'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
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
import { formatScalar } from '@/shared/units'

type Format = string | [string, number, number]

/** 형식 이름 하나로 칸 형식 값을 만든다 — 고정폭은 폭·자릿수가 함께 있어야 뜻이 선다. */
function formatOf(name: string, was?: Format): Format {
  if (!name.startsWith('fixed')) return name
  return [name, Array.isArray(was) ? was[1] : 20, Array.isArray(was) ? was[2] : 9]
}

function formatName(format?: Format): string {
  return Array.isArray(format) ? format[0] : (format ?? 'free')
}

function emptySection(keyword = ''): Section {
  return {
    keyword: { kind: 'text', text: keyword },
    body: [],
    when: '',
    mixedWhen: false,
    note: '',
  }
}

export default function ExportProfileEditorPage() {
  const { key } = useParams<{ key: string }>()
  const navigate = useNavigate()
  const editing = Boolean(key)

  const [profileKey, setProfileKey] = useState(key ?? '')
  const [label, setLabel] = useState('')
  const [extension, setExtension] = useState('inp')
  const [describe, setDescribe] = useState('')
  const [sections, setSections] = useState<Section[]>([emptySection()])
  // **칸 형식은 정의에서 한 번 고른다.** 칸마다 고르게 했더니 스무 칸을 스무 번 골랐다 —
  // 솔버는 하나의 형식을 쓴다. 칸별 예외는 「고급」 에 남긴다.
  const [formatDefault, setFormatDefault] = useState('free')
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set())
  const [hovered, setHovered] = useState<number | null>(null)
  const [wizard, setWizard] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [saving, setSaving] = useState(false)
  const [scanNotes, setScanNotes] = useState<string[]>([])

  // **실물 카드라야 뜻이 있다** — 지어낸 값으로는 「이 카드에는 밀도가 없다」 같은 것이
  // 안 드러난다.
  const cards = useResource(() => fittingApi.cards({ limit: 20 }), [])
  // 블록 이름을 사람이 읽는 말로. **화면이 `elastic`·`viscoelastic` 을 몰라야 한다** —
  // 그것이 새 물성을 확장으로 붙일 수 있는 이유다.
  const specs = useResource(() => fittingApi.blocks(), [])
  // **미리보기도 단위계를 고른다.** 늘 SI 로 그렸더니 화면(mm·N·tonne)과 달라 「단위가
  // 이상하다」 가 됐다(2026-09-05). 기본은 서버가 기본이라고 말한 계 — 내려받기와 같다.
  const systems = useResource(() => fittingApi.unitSystems(), [])
  const [unitsKey, setUnitsKey] = useState<string | null>(null)
  const units =
    unitsKey ?? systems.data?.find((one) => one.is_default)?.key ?? systems.data?.[0]?.key ?? null
  const [cardId, setCardId] = useState<string>('')
  const [preview, setPreview] = useState<DeckPreview | null>(null)
  // **고른 카드에 무엇이 들어 있는가.** 값을 고르는 자리와 「넣기」 가 이것을 읽는다.
  const cardKeys = useResource(
    () => (cardId ? fittingApi.deckKeys(cardId) : Promise.resolve(null)),
    [cardId]
  )
  const [picking, setPicking] = useState(false)
  const [pickedName, setPickedName] = useState<string | null>(null)

  // 고치러 들어온 경우 저장된 정의를 폼으로 편다.
  const existing = useResource(
    async () =>
      key ? ((await fittingApi.exportProfiles()).find((one) => one.key === key) ?? null) : null,
    [key]
  )
  useEffect(() => {
    const found = existing.data as ExportProfile | null
    if (!found) return
    const definition = found.definition as Record<string, unknown>
    setLabel(found.label)
    setExtension(String(definition.extension ?? 'inp'))
    setDescribe(String(definition.describe ?? ''))
    const raw = Array.isArray(definition.lines) ? definition.lines : []
    const lines = raw.map((one) => fromDefinitionLine(one as Record<string, unknown>))
    setSections(toSections(lines))
    // 저장해 둔 기본 형식이 없으면 가장 많이 쓴 형식으로 본다.
    if (typeof definition.field_format === 'string') setFormatDefault(definition.field_format)
    else {
      const seen = new Map<string, number>()
      for (const line of lines)
        for (const field of line.fields ?? [])
          seen.set(formatName(field.format), (seen.get(formatName(field.format)) ?? 0) + 1)
      const top = [...seen.entries()].sort((a, b) => b[1] - a[1])[0]
      if (top) setFormatDefault(top[0])
    }
  }, [existing.data])

  useEffect(() => {
    if (cardId) return
    // **값이 가장 많은 카드로 시작한다.** 목록 첫 장을 잡으면 그것이 탄성만 든 카드일 수
    // 있고, 그러면 미리보기가 계속 「값이 없다」 를 내는데 사람은 정의를 의심한다.
    const richest = [...(cards.data?.items ?? [])].sort(
      (a, b) => Object.keys(b.blocks ?? {}).length - Object.keys(a.blocks ?? {}).length
    )[0]
    if (richest) setCardId(richest.id)
  }, [cards.data, cardId])

  const lines = useMemo(() => fromSections(sections), [sections])
  const ranges = useMemo(() => lineRanges(sections), [sections])
  const definition = useMemo(
    () => ({
      extension,
      describe: describe || '해석용 물성 정의',
      field_format: formatDefault,
      lines: lines.map(toDefinitionLine),
    }),
    [extension, describe, formatDefault, lines]
  )

  // **적는 대로 그려 본다.** 저장을 눌러야 알게 하면 그때는 이미 고칠 마음이 식는다.
  useEffect(() => {
    if (!cardId || !units) return
    let alive = true
    const timer = setTimeout(() => {
      void fittingApi
        .previewDeck({ ...definition, label: label || '덱' }, cardId, units)
        .then((got) => {
          if (alive) setPreview(got)
        })
        .catch((caught: unknown) => {
          if (alive) {
            setPreview({
              text: null,
              error: caught instanceof Error ? caught.message : '미리보기에 실패했습니다.',
              missing: [],
              notes: [],
              spans: [],
            })
          }
        })
    }, 400)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [definition, cardId, label, units])

  /** 마우스를 올린 묶음이 만든 덱의 줄 번호들. */
  const highlighted = useMemo(() => {
    const found = new Set<number>()
    if (hovered === null || !preview?.spans) return found
    const range = ranges[hovered]
    if (!range) return found
    for (const [index, start, end] of preview.spans) {
      if (index >= range.start && index < range.end) {
        for (let at = start; at < end; at += 1) found.add(at)
      }
    }
    return found
  }, [hovered, preview?.spans, ranges])

  async function readExample(file: File) {
    setError(null)
    try {
      const found = await fittingApi.scanDeck(await file.text(), cardId || undefined)
      setSections(toSections(fromScan(found)))
      setScanNotes(found.notes ?? [])
      const dot = file.name.lastIndexOf('.')
      if (dot > 0) setExtension(file.name.slice(dot + 1))
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('예제 덱을 읽지 못했습니다.'))
    }
  }

  function describeCard(one: PropertyCard): string {
    const kinds = Object.keys(one.blocks ?? {})
      .map((k) => specs.data?.find((spec) => spec.key === k)?.label ?? k)
      .join(' · ')
    const where = [one.material_name, one.orientation].filter(Boolean).join(' · ')
    return [where, kinds || '값 없음'].filter(Boolean).join(' — ')
  }

  // ── 묶음·줄 고치기 ────────────────────────────────────────────────────────
  function patchSection(index: number, change: Partial<Section>) {
    setSections((old) => old.map((one, at) => (at === index ? { ...one, ...change } : one)))
  }
  function patchLine(index: number, at: number, change: Partial<DeckLine>) {
    setSections((old) =>
      old.map((one, i) =>
        i === index
          ? { ...one, body: one.body.map((line, j) => (j === at ? { ...line, ...change } : line)) }
          : one
      )
    )
  }
  function patchField(index: number, at: number, field: number, change: Partial<FieldSpec>) {
    setSections((old) =>
      old.map((one, i) =>
        i === index
          ? {
              ...one,
              body: one.body.map((line, j) =>
                j === at
                  ? {
                      ...line,
                      fields: (line.fields ?? []).map((f, k) =>
                        k === field ? { ...f, ...change } : f
                      ),
                    }
                  : line
              ),
            }
          : one
      )
    )
  }
  function addLine(index: number, kind: LineKind) {
    const line = blank(kind)
    for (const field of line.fields ?? []) field.format = formatOf(formatDefault)
    setSections((old) =>
      old.map((one, i) => (i === index ? { ...one, body: [...one.body, line] } : one))
    )
  }
  function moveSection(index: number, by: number) {
    // **차례가 곧 덱이다.** 키워드 순서가 바뀌면 솔버가 다르게 읽는다.
    setSections((old) => {
      const to = index + by
      if (to < 0 || to >= old.length) return old
      const next = [...old]
      const [taken] = next.splice(index, 1)
      next.splice(to, 0, taken)
      return next
    })
  }

  /**
   * 값 하나를 정의에 넣는다. **마지막 묶음의 마지막 값 줄에 칸을 더하고, 없으면 값 줄을
   * 만든다.** 어느 줄에 넣을지 매번 묻게 하면 「이 카드에 든 것」 이 목록으로 그친다.
   */
  function putValue(path: string) {
    setSections((old) => {
      const list = old.length ? [...old] : [emptySection()]
      const last = { ...list[list.length - 1], body: [...list[list.length - 1].body] }
      const at = [...last.body].reverse().findIndex((one) => one.kind === 'fields')
      const field = { value: path, format: formatOf(formatDefault) }
      if (at === -1) last.body.push({ kind: 'fields', fields: [field] })
      else {
        const index = last.body.length - 1 - at
        const line = last.body[index]
        last.body[index] = {
          ...line,
          fields: [
            ...(line.fields ?? []).filter((f) => f.value !== '' || f.const !== undefined),
            field,
          ],
        }
      }
      list[list.length - 1] = last
      return list
    })
  }

  function putTable(block: string, columns: string[]) {
    const spec = specs.data?.find((one) => one.key === block)
    setSections((old) => {
      const list = old.length ? [...old] : [emptySection()]
      const last = { ...list[list.length - 1], body: [...list[list.length - 1].body] }
      last.body.push(tableLine(block, columns, spec))
      list[list.length - 1] = last
      return list
    })
  }

  /** 표 줄. **점 곡선인지는 블록 선언이 말한다**(`curve`) — 열 수로 짐작하면 두 열짜리
   *  Prony 표를 정렬해 다른 재료로 만든다. */
  function tableLine(block: string, columns: string[], spec?: BlockSpec): DeckLine {
    const curve = spec?.curve ?? null
    return {
      kind: 'rows',
      rows: block,
      ...(curve ? { x: curve[0], y: curve[1] } : {}),
      fields: columns.map((value) => ({ value, format: formatOf(formatDefault) })),
    }
  }

  /** 정의가 참조하는 블록 — 카드 후보를 이것으로 가른다. */
  const referencedBlocks = useMemo(() => {
    const found = new Set<string>()
    for (const line of lines) {
      if (line.kind === 'rows' && line.rows) found.add(line.rows)
      if (line.kind === 'block' && line.block && line.block !== 'header') found.add(line.block)
      for (const field of line.fields ?? []) {
        if (line.kind === 'fields' && field.value?.includes('.')) found.add(field.value.split('.')[0])
      }
    }
    return found
  }, [lines])
  const cardOptions = useMemo(() => {
    const items = cards.data?.items ?? []
    const score = (one: PropertyCard) =>
      [...referencedBlocks].filter((block) => block in (one.blocks ?? {})).length
    return [...items].sort((a, b) => score(b) - score(a))
  }, [cards.data, referencedBlocks])

  async function save() {
    setError(null)
    setSaving(true)
    try {
      if (editing && key) {
        await fittingApi.saveExportProfile(key, { label, definition, is_active: true })
      } else {
        await fittingApi.createExportProfile({ key: profileKey, label, definition, is_active: true })
      }
      navigate('/settings/export-profiles')
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  const previewLines = (preview?.text ?? '').split('\n')

  return (
    <div>
      <PageHeader
        sticky
        title={editing ? `해석용 물성 정의 · ${key}` : '해석용 물성 정의 생성'}
        description="물성 묶음을 쌓습니다. 오른쪽은 고른 카드로 지금 정의를 실제로 그려 본 것입니다 — 저장하기 전에 봅니다."
        actions={
          <Button onClick={() => void save()} disabled={saving || !label || !profileKey}>
            저장
          </Button>
        }
      />

      {error ? <ErrorNotice error={error} className="mb-4" /> : null}

      <CardPickerDialog
        open={picking}
        onOpenChange={setPicking}
        specs={specs.data ?? []}
        current={cardId}
        onPick={(card) => {
          setCardId(card.id)
          setPickedName(describeCard(card))
        }}
      />

      <BlockWizard
        open={wizard}
        specs={specs.data ?? []}
        cardKeys={cardKeys.data ?? null}
        onClose={() => setWizard(false)}
        onAdd={(section) => {
          setSections((old) => [...old, section])
          setWizard(false)
        }}
        formatDefault={formatDefault}
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,6fr)_minmax(0,4fr)]">
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="space-y-1.5">
              <Label className="text-xs">key</Label>
              <Input
                className="h-8 font-mono text-xs"
                value={profileKey}
                disabled={editing}
                onChange={(event) => setProfileKey(event.target.value)}
                placeholder="optistruct"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">이름</Label>
              <Input
                className="h-8"
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                placeholder="OptiStruct 탄소성"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">확장자</Label>
              <Input
                className="h-8 font-mono text-xs"
                value={extension}
                onChange={(event) => setExtension(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">칸 형식 (기본)</Label>
              <Select value={formatDefault} onValueChange={setFormatDefault}>
                <SelectTrigger className="h-8" aria-label="칸 형식 기본">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FORMATS.map((one) => (
                    <SelectItem key={one.key} value={one.key}>
                      {one.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* **빈 폼에서 시작하지 않게.** 블록 하나로 묶음 초안이, 파일 하나로 줄·칸 폭이 온다. */}
          <div className="bg-muted/40 rounded-md border border-dashed p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="default" size="sm" onClick={() => setWizard(true)}>
                <Layers className="size-4" />
                물성 묶음 추가
              </Button>
              <Button variant="outline" size="sm" asChild>
                <label className="cursor-pointer">
                  <Upload className="size-4" />
                  {lines.length > 1 ? '예제 덱으로 다시 시작' : '예제 덱에서 시작'}
                  <input
                    type="file"
                    className="hidden"
                    aria-label="예제 덱 파일"
                    onChange={(event) => {
                      const file = event.target.files?.[0]
                      if (file) void readExample(file)
                      event.target.value = ''
                    }}
                  />
                </label>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSections((old) => [...old, emptySection()])}
              >
                <Plus className="size-3" />빈 묶음
              </Button>
              <span className="text-muted-foreground text-xs">
                묶음 = 키워드 한 줄 + 그 아래 값·표. 블록을 고르면 값 이름을 적지 않아도 됩니다.
              </span>
            </div>
            {scanNotes.length ? (
              <ul className="text-muted-foreground mt-2 space-y-1 text-xs">
                {scanNotes.map((one, at) => (
                  <li key={at}>· {one}</li>
                ))}
              </ul>
            ) : null}
          </div>

          <div className="space-y-2">
            {sections.map((section, index) => {
              const n = index + 1
              const range = ranges[index]
              const lineNo = (at: number) => range.start + (section.keyword ? 1 : 0) + at + 1
              const open = !collapsed.has(index)
              return (
                <section
                  key={index}
                  className={`rounded-md border p-3 ${hovered === index ? 'border-amber-400' : ''}`}
                  aria-label={`${n}번 묶음`}
                  onMouseEnter={() => setHovered(index)}
                  onMouseLeave={() => setHovered((now) => (now === index ? null : now))}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      className="text-muted-foreground flex size-6 items-center justify-center"
                      aria-label={`${n}번 묶음 ${open ? '접기' : '펼치기'}`}
                      onClick={() =>
                        setCollapsed((now) => {
                          const next = new Set(now)
                          if (next.has(index)) next.delete(index)
                          else next.add(index)
                          return next
                        })
                      }
                    >
                      {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                    </button>
                    <span className="text-muted-foreground w-5 text-xs">{n}</span>
                    {section.keyword ? (
                      <Input
                        className="h-8 min-w-48 flex-1 font-mono text-xs"
                        value={section.keyword.text ?? ''}
                        onChange={(event) =>
                          patchSection(index, {
                            keyword: { ...section.keyword, kind: 'text', text: event.target.value },
                          })
                        }
                        placeholder="*ELASTIC  ({name}·{units} 를 쓸 수 있습니다)"
                        aria-label={`${n}번 묶음 키워드`}
                      />
                    ) : (
                      <span className="text-muted-foreground flex items-center gap-2 text-xs">
                        키워드 없음
                        {section.body.some((one) => one.kind !== 'block') && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-xs"
                            onClick={() =>
                              patchSection(index, { keyword: { kind: 'text', text: '' } })
                            }
                          >
                            키워드 줄 추가
                          </Button>
                        )}
                      </span>
                    )}
                    <span className="text-muted-foreground text-xs">{summarize(section)}</span>
                    <span className="ml-auto flex gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        title="위로"
                        aria-label={`${n}번 묶음 위로`}
                        onClick={() => moveSection(index, -1)}
                      >
                        <ArrowUp className="size-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        title="아래로"
                        aria-label={`${n}번 묶음 아래로`}
                        onClick={() => moveSection(index, 1)}
                      >
                        <ArrowDown className="size-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        title="묶음 삭제"
                        aria-label={`${n}번 묶음 삭제`}
                        onClick={() => setSections((old) => old.filter((_, at) => at !== index))}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </span>
                  </div>

                  {open && (
                    <div className="mt-2 space-y-2 pl-8">
                      {section.body.map((line, at) => (
                        <LineEditor
                          key={at}
                          line={line}
                          lineNo={lineNo(at)}
                          specs={specs.data ?? []}
                          cardKeys={cardKeys.data ?? null}
                          formatDefault={formatDefault}
                          onChange={(change) => patchLine(index, at, change)}
                          onField={(field, change) => patchField(index, at, field, change)}
                          onRemove={() =>
                            patchSection(index, { body: section.body.filter((_, j) => j !== at) })
                          }
                        />
                      ))}
                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => addLine(index, 'fields')}
                        >
                          <Plus className="size-3" />
                          {n}번 묶음에 값 줄
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => addLine(index, 'rows')}
                        >
                          <Plus className="size-3" />
                          {n}번 묶음에 표 줄
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          title="카드 값이 안 드는 줄 — 옵션 숫자·플래그·주석. 적은 그대로 나갑니다."
                          onClick={() => addLine(index, 'plain')}
                        >
                          <Plus className="size-3" />
                          {n}번 묶음에 글자 줄
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => addLine(index, 'block')}
                        >
                          <Plus className="size-3" />
                          {n}번 묶음에 코드 묶음
                        </Button>
                      </div>

                      {/* **있으면 넣고 없으면 빼기 — 묶음에 한 번.** 밀도가 그렇다. 뺐다는 사실은
                          덱 주석과 사람에게 남긴다. */}
                      <div className="grid gap-2 sm:grid-cols-2">
                        <div className="flex items-center gap-1">
                          <Input
                            className="h-8 flex-1 font-mono text-xs"
                            value={section.when}
                            disabled={section.mixedWhen}
                            onChange={(event) => patchSection(index, { when: event.target.value })}
                            placeholder={
                              section.mixedWhen ? '줄마다 조건이 다릅니다' : '조건 (선택) — 값이 있을 때만'
                            }
                            aria-label={`${n}번 묶음 조건`}
                          />
                          {!section.mixedWhen && (
                            <DeckKeyPicker
                              specs={specs.data ?? []}
                              cardKeys={cardKeys.data ?? null}
                              target="value"
                              label={`${n}번 묶음 조건 값 선택`}
                              onPick={(path) =>
                                patchSection(index, {
                                  when: section.when.startsWith('missing:') ? `missing:${path}` : path,
                                })
                              }
                            />
                          )}
                          {section.when && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 text-xs"
                              title="이 값이 있을 때 그릴지, 없을 때 그릴지"
                              onClick={() =>
                                patchSection(index, {
                                  when: section.when.startsWith('missing:')
                                    ? section.when.slice('missing:'.length)
                                    : `missing:${section.when}`,
                                })
                              }
                            >
                              {section.when.startsWith('missing:') ? '없을 때' : '있을 때'}
                            </Button>
                          )}
                        </div>
                        <Input
                          className="h-8 text-xs"
                          value={section.note}
                          onChange={(event) => patchSection(index, { note: event.target.value })}
                          placeholder="사람에게 남길 말 (선택)"
                          aria-label={`${n}번 묶음 안내`}
                        />
                      </div>
                    </div>
                  )}
                </section>
              )
            })}
          </div>
        </div>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label className="text-xs">미리보기에 쓸 카드 (최근 20장)</Label>
            <div className="flex gap-2">
              <Select
                value={cardId}
                onValueChange={(value) => {
                  setCardId(value)
                  setPickedName(null)
                }}
              >
                <SelectTrigger className="h-8 flex-1" aria-label="미리보기 카드">
                  <SelectValue placeholder="카드를 고르세요">{pickedName ?? undefined}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {cardOptions.map((one) => (
                    <SelectItem key={one.id} value={one.id}>
                      {describeCard(one)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button variant="outline" size="sm" className="h-8" onClick={() => setPicking(true)}>
                <Search className="size-4" />
                상세
              </Button>
            </div>
            <p className="text-muted-foreground text-xs">
              이 카드의 값으로 덱을 그려 봅니다. 정의가 쓰는 값이 든 카드가 목록 앞에 옵니다.
            </p>
            {cards.data && cards.data.items.length === 0 ? (
              <p className="text-muted-foreground rounded-md border border-dashed p-3 text-xs">
                아직 물성 카드가 없습니다. 카드를 하나 만들면 여기서 덱을 그려 볼 수 있습니다.
              </p>
            ) : null}
          </div>

          {/* **이 카드에 든 것.** 정의가 무엇을 집을 수 있는지 카드 쪽에서 본다 — 「Prony
              계수가 있는 카드는 어떻게 받나」 의 답이 여기 있다: 점탄성 표와 그 열. */}
          {cardKeys.data && (
            <CardContents keys={cardKeys.data} onValue={putValue} onTable={putTable} />
          )}

          {preview?.error ? (
            <p className="border-destructive/40 bg-destructive/5 text-destructive rounded-md border p-3 text-sm">
              {preview.error}
            </p>
          ) : null}

          {preview?.missing?.length ? (
            <p className="text-muted-foreground rounded-md border border-dashed p-3 text-sm">
              이 카드에 없는 값: {preview.missing.join(', ')} — 정의가 아니라 카드 쪽입니다. 다른
              카드로 봐 주세요.
            </p>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <Label className="text-xs">덱 단위계</Label>
            <Select value={units ?? ''} onValueChange={setUnitsKey}>
              <SelectTrigger className="h-8 w-64" aria-label="덱 단위계">
                <SelectValue placeholder="단위계" />
              </SelectTrigger>
              <SelectContent>
                {(systems.data ?? []).map((one) => (
                  <SelectItem key={one.key} value={one.key}>
                    {one.label}
                    {one.is_default ? ' · 기본' : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-muted-foreground text-xs">
              내려받을 때 고르는 것과 같습니다. 덱 머리에 계가 선언됩니다.
            </span>
          </div>

          {/* 묶음에 마우스를 올리면 그 묶음이 만든 줄이 강조된다. */}
          <pre
            className="bg-muted max-h-[60vh] overflow-auto rounded-md p-3 font-mono text-xs"
            aria-label="덱 미리보기"
          >
            {preview?.text
              ? previewLines.map((text, at) => (
                  <span
                    key={at}
                    className={`block ${highlighted.has(at) ? 'bg-amber-200/70 dark:bg-amber-900/60' : ''}`}
                  >
                    {text || ' '}
                  </span>
                ))
              : '카드를 고르면 여기에 덱이 나옵니다.'}
          </pre>

          {preview?.notes?.length ? (
            <ul className="text-muted-foreground space-y-1 text-xs">
              {preview.notes.map((one, at) => (
                <li key={at}>· {one}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </div>
  )
}

/** 줄 하나 — 값 줄·표 줄·코드 묶음. 접두·구분자·칸별 형식은 「고급」 에 접어 둔다. */
function LineEditor({
  line,
  lineNo,
  specs,
  cardKeys,
  formatDefault,
  onChange,
  onField,
  onRemove,
}: {
  line: DeckLine
  lineNo: number
  specs: BlockSpec[]
  cardKeys: DeckKeys | null
  formatDefault: string
  onChange: (change: Partial<DeckLine>) => void
  onField: (field: number, change: Partial<FieldSpec>) => void
  onRemove: () => void
}) {
  const kindLabel =
    line.kind === 'fields'
      ? '값'
      : line.kind === 'rows'
        ? '표'
        : line.kind === 'plain'
          ? '글자'
          : '코드 묶음'
  return (
    <div className="rounded-md border border-dashed p-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground w-5 text-xs">{lineNo}</span>
        <span className="rounded bg-muted px-1.5 py-0.5 text-xs">{kindLabel}</span>

        {line.kind === 'plain' && (
          // **카드 값이 안 드는 줄.** 옵션 숫자·플래그·주석이 그렇다 — 적은 그대로 나간다.
          <Input
            className="h-8 flex-1 font-mono text-xs"
            value={line.text ?? ''}
            onChange={(event) => onChange({ text: event.target.value })}
            placeholder="그대로 나갈 글자 — 1, 0, 0"
            aria-label={`${lineNo}번 줄 글자`}
          />
        )}

        {line.kind === 'block' && (
          <Select value={line.block ?? 'header'} onValueChange={(value) => onChange({ block: value })}>
            <SelectTrigger className="h-8 flex-1" aria-label={`${lineNo}번 줄 묶음`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {BLOCKS.map((one) => (
                <SelectItem key={one.key} value={one.key}>
                  {one.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {line.kind === 'rows' && (
          <>
            <Select value={line.rows ?? ''} onValueChange={(value) => onChange({ rows: value })}>
              <SelectTrigger className="h-8 w-52" aria-label={`${lineNo}번 줄 표 이름`}>
                <SelectValue placeholder="표" />
              </SelectTrigger>
              <SelectContent>
                {specs
                  .filter((spec) => spec.rows.length > 0)
                  .map((spec) => (
                    <SelectItem key={spec.key} value={spec.key}>
                      {spec.label} <span className="font-mono text-xs">({spec.key})</span>
                    </SelectItem>
                  ))}
                {line.rows && !specs.some((spec) => spec.key === line.rows) && (
                  <SelectItem value={line.rows}>{line.rows}</SelectItem>
                )}
              </SelectContent>
            </Select>
            <Input
              className="h-8 w-28 font-mono text-xs"
              value={line.x ?? ''}
              onChange={(event) => onChange({ x: event.target.value })}
              placeholder="x (점 표)"
              aria-label={`${lineNo}번 줄 x 열`}
            />
            <Input
              className="h-8 w-28 font-mono text-xs"
              value={line.y ?? ''}
              onChange={(event) => onChange({ y: event.target.value })}
              placeholder="y (점 표)"
              aria-label={`${lineNo}번 줄 y 열`}
            />
          </>
        )}

        <Button
          variant="ghost"
          size="icon"
          className="ml-auto"
          title="줄 삭제"
          aria-label={`${lineNo}번 줄 삭제`}
          onClick={onRemove}
        >
          <Trash2 className="size-4" />
        </Button>
      </div>

      {(line.kind === 'fields' || line.kind === 'rows') && (
        <div className="mt-2 space-y-1.5 pl-7">
          {(line.fields ?? []).map((field, at) => {
            const kind = field.const !== undefined ? 'const' : field.expr !== undefined ? 'expr' : 'value'
            return (
            <div key={at} className="flex items-center gap-2">
              {kind !== 'value' && (
                <span className="rounded bg-muted px-1.5 py-0.5 text-xs" title={kind === 'expr' ? '계산해서 적는 칸' : '늘 같은 글자를 적는 칸'}>
                  {kind === 'expr' ? '식' : '상수'}
                </span>
              )}
              <Input
                className="h-8 flex-1 font-mono text-xs"
                value={field.const ?? field.expr ?? field.value ?? ''}
                onChange={(event) => onField(at, { [kind]: event.target.value } as Partial<FieldSpec>)}
                placeholder={
                  kind === 'expr'
                    ? line.kind === 'rows'
                      ? '식 — true_stress / 1000'
                      : '식 — elastic.youngs_modulus / (2 * (1 + elastic.poisson_ratio))'
                    : line.kind === 'rows'
                      ? '열 이름'
                      : '블록.값'
                }
                title={
                  kind === 'expr'
                    ? '사칙연산 · ^ · 괄호 · sqrt abs exp log log10 min max. 열 이름은 표 줄에서, 블록.값은 어디서나.'
                    : undefined
                }
                aria-label={`${lineNo}번 줄 ${at + 1}번 칸`}
              />
              {kind !== 'const' && (
                <DeckKeyPicker
                  specs={specs}
                  cardKeys={cardKeys}
                  target={line.kind === 'rows' ? 'column' : 'value'}
                  table={line.rows}
                  label={`${lineNo}번 줄 ${at + 1}번 칸 선택`}
                  onPick={(path) =>
                    kind === 'expr'
                      ? // 식에는 **끼워 넣는다** — 고른 값이 식의 재료다.
                        onField(at, { expr: `${field.expr ?? ''}${field.expr ? ' ' : ''}${path}` })
                      : onField(at, { value: path })
                  }
                />
              )}
              {kind === 'value' && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 text-xs"
                  title="이 값을 계산해서 적는다 — 열 / 1000 같은 것"
                  aria-label={`${lineNo}번 줄 ${at + 1}번 칸 식으로`}
                  onClick={() => onField(at, { expr: field.value ?? '', value: undefined })}
                >
                  계산
                </Button>
              )}
              {formatName(field.format) !== formatDefault && (
                <span className="text-muted-foreground text-xs" title="이 칸만 다른 형식">
                  {formatName(field.format)}
                </span>
              )}
              <Button
                variant="ghost"
                size="icon"
                title="칸 삭제"
                onClick={() => onChange({ fields: (line.fields ?? []).filter((_, j) => j !== at) })}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
            )
          })}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={() =>
                onChange({
                  fields: [...(line.fields ?? []), { value: '', format: formatOf(formatDefault) }],
                })
              }
            >
              <Plus className="size-3" />칸 추가
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              title="카드 값이 아니라 늘 같은 글자를 적는 칸 — 재료 번호, Prony 의 체적항"
              onClick={() => onChange({ fields: [...(line.fields ?? []), { const: '' }] })}
            >
              <Plus className="size-3" />상수 칸
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              title="값·열을 계산해서 적는 칸 — 열 / 1000, E / (2 * (1 + ν))"
              onClick={() =>
                onChange({
                  fields: [...(line.fields ?? []), { expr: '', format: formatOf(formatDefault) }],
                })
              }
            >
              <Plus className="size-3" />식 칸
            </Button>
          </div>

          {/* **고급.** 접두·구분자·칸별 형식은 솔버에 따라 필요한데, 늘 보이면 열 칸 중
              아홉 칸의 일이 아닌 것이 화면을 채운다. */}
          <details className="text-xs">
            <summary className="text-muted-foreground cursor-pointer">
              고급 — 접두 · 구분자 · 칸별 형식
            </summary>
            <div className="mt-2 grid gap-2 sm:grid-cols-3">
              <Input
                className="h-8 font-mono text-xs"
                value={line.prefix ?? ''}
                onChange={(event) => onChange({ prefix: event.target.value })}
                placeholder="접두 — MP,EX,"
                aria-label={`${lineNo}번 줄 접두`}
              />
              <Input
                className="h-8 font-mono text-xs"
                value={line.join ?? ''}
                onChange={(event) => onChange({ join: event.target.value })}
                placeholder="구분자 (기본 ', ')"
                aria-label={`${lineNo}번 줄 구분자`}
              />
              <Input
                className="h-8 font-mono text-xs"
                value={line.suffix ?? ''}
                onChange={(event) => onChange({ suffix: event.target.value })}
                placeholder="접미"
                aria-label={`${lineNo}번 줄 접미`}
              />
            </div>
            <div className="mt-2 space-y-1">
              {(line.fields ?? []).map((field, at) => (
                <div key={at} className="flex items-center gap-2">
                  <span className="text-muted-foreground w-24 truncate font-mono">
                    {fieldLabel(field, at)}
                  </span>
                  <Select
                    value={formatName(field.format)}
                    onValueChange={(value) => onField(at, { format: formatOf(value, field.format) })}
                  >
                    <SelectTrigger className="h-7 w-64" aria-label={`${lineNo}번 줄 ${at + 1}번 칸 형식`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {FORMATS.map((one) => (
                        <SelectItem key={one.key} value={one.key}>
                          {one.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {Array.isArray(field.format) && (
                    <>
                      <Input
                        className="h-7 w-16 font-mono text-xs"
                        value={field.format[1]}
                        onChange={(event) =>
                          onField(at, {
                            format: [
                              (field.format as [string, number, number])[0],
                              Number(event.target.value) || 0,
                              (field.format as [string, number, number])[2],
                            ],
                          })
                        }
                        aria-label={`${lineNo}번 줄 ${at + 1}번 칸 폭`}
                      />
                      <Input
                        className="h-7 w-16 font-mono text-xs"
                        value={field.format[2]}
                        onChange={(event) =>
                          onField(at, {
                            format: [
                              (field.format as [string, number, number])[0],
                              (field.format as [string, number, number])[1],
                              Number(event.target.value) || 0,
                            ],
                          })
                        }
                        aria-label={`${lineNo}번 줄 ${at + 1}번 칸 자릿수`}
                      />
                    </>
                  )}
                </div>
              ))}
            </div>
          </details>
        </div>
      )}
    </div>
  )
}

/** 고른 카드에 든 값·표. 「넣기」 가 정의에 칸을 더한다. */
function CardContents({
  keys,
  onValue,
  onTable,
}: {
  keys: DeckKeys
  onValue: (path: string) => void
  onTable: (block: string, columns: string[]) => void
}) {
  const blocks = Array.from(new Set(keys.values.map((one) => one.block)))
  return (
    <section className="space-y-2 rounded-md border p-3" aria-label="이 카드에 든 것">
      <p className="text-xs font-medium">이 카드에 든 것</p>
      {blocks.map((block) => {
        const rows = keys.values.filter((one) => one.block === block)
        return (
          <div key={block}>
            <p className="text-muted-foreground text-xs">{rows[0]?.block_label ?? block}</p>
            <ul className="space-y-0.5">
              {rows.map((one) => (
                <li key={one.path} className="flex items-center gap-2 text-xs">
                  <span>{one.label}</span>
                  <span className="font-mono tabular-nums">
                    {formatScalar(one.value, one.si_unit ?? null)}
                  </span>
                  <span className="text-muted-foreground font-mono">{one.path}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-auto h-6 px-2 text-xs"
                    aria-label={`${one.label} 입력`}
                    title="마지막 묶음의 값 줄에 칸으로 넣습니다"
                    onClick={() => onValue(one.path)}
                  >
                    <Plus className="size-3" />
                    입력
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
      {keys.tables.map((table) => (
        <div key={table.block}>
          <p className="text-muted-foreground text-xs">
            {table.block_label} 표 · {table.row_count}행 ·{' '}
            {table.columns.map((one) => one.label).join(' · ')}
          </p>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
            aria-label={`${table.block_label} 표 줄 추가`}
            title="이 표를 열 전부와 함께 표 줄로 넣습니다"
            onClick={() =>
              onTable(
                table.block,
                table.columns.map((one) => one.key)
              )
            }
          >
            <Plus className="size-3" />표 줄 추가
          </Button>
        </div>
      ))}
      {keys.values.length === 0 && keys.tables.length === 0 && (
        <p className="text-muted-foreground text-xs">이 카드에는 덱에 꽂을 값이 없습니다.</p>
      )}
    </section>
  )
}

/**
 * 물성 묶음 마법사 — **블록에서 출발한다.** 블록을 고르면 값·표가 채워지고, 사람은
 * 키워드와 「어느 값을 넣을까」 만 정한다. 값이 없을 수 있는 묶음(밀도)은 첫 값을
 * 조건으로 걸어 「없으면 뺀다」 가 기본이다.
 */
function BlockWizard({
  open,
  specs,
  cardKeys,
  formatDefault,
  onClose,
  onAdd,
}: {
  open: boolean
  specs: BlockSpec[]
  /** 고른 카드에 든 것. 있으면 **그 카드에 있는 값만 기본으로 켠다** — 없는 값을 켜 두면
   *  덱이 안 나온다(`shift_method` 같은 글자 값이 그렇다). */
  cardKeys: DeckKeys | null
  formatDefault: string
  onClose: () => void
  onAdd: (section: Section) => void
}) {
  const [blockKey, setBlockKey] = useState('')
  const [keyword, setKeyword] = useState('')
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [withTable, setWithTable] = useState(true)
  const [guard, setGuard] = useState(true)
  const spec = specs.find((one) => one.key === blockKey) ?? null

  useEffect(() => {
    if (!open) return
    setBlockKey('')
    setKeyword('')
    setPicked(new Set())
    setWithTable(true)
    setGuard(true)
  }, [open])

  const inCard = cardKeys ? new Set(cardKeys.values.map((one) => one.path)) : null
  function choose(key: string) {
    setBlockKey(key)
    const found = specs.find((one) => one.key === key)
    setPicked(
      new Set(
        (found?.produces ?? [])
          .filter((one) => !inCard || inCard.has(`${key}.${one.key}`))
          .map((one) => one.key)
      )
    )
  }

  function add() {
    if (!spec) return
    const values = spec.produces.filter((one) => picked.has(one.key))
    const body: DeckLine[] = []
    if (values.length > 0) {
      body.push({
        kind: 'fields',
        fields: values.map((one) => ({
          value: `${spec.key}.${one.key}`,
          format: formatOf(formatDefault),
        })),
      })
    }
    if (withTable && spec.rows.length > 0) {
      const columns = spec.rows.map((one) => one.key)
      const curve = spec.curve ?? null
      body.push({
        kind: 'rows',
        rows: spec.key,
        ...(curve ? { x: curve[0], y: curve[1] } : {}),
        fields: columns.map((value) => ({ value, format: formatOf(formatDefault) })),
      })
    }
    onAdd({
      keyword: keyword.trim() ? { kind: 'text', text: keyword.trim() } : null,
      body,
      when: guard && values[0] ? `${spec.key}.${values[0].key}` : '',
      mixedWhen: false,
      note: '',
    })
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>물성 묶음 추가</DialogTitle>
          <DialogDescription>
            블록을 고르면 그 블록의 값·표가 채워집니다. 키워드 줄과 넣을 값만 정하세요.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label className="text-xs">블록</Label>
            <select
              aria-label="블록"
              className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
              value={blockKey}
              onChange={(event) => choose(event.target.value)}
            >
              <option value="">고르세요</option>
              {specs.map((one) => (
                <option key={one.key} value={one.key}>
                  {one.label} — 값 {one.produces.length}
                  {one.rows.length > 0 ? ` · 표 열 ${one.rows.length}` : ''}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">키워드 줄 (선택)</Label>
            <Input
              className="h-8 font-mono text-xs"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="*ELASTIC"
              aria-label="묶음 키워드"
            />
          </div>
          {spec && spec.produces.length > 0 && (
            <div className="space-y-1">
              <Label className="text-xs">넣을 값</Label>
              {spec.produces.map((one) => (
                <label key={one.key} className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={picked.has(one.key)}
                    onChange={(event) =>
                      setPicked((now) => {
                        const next = new Set(now)
                        if (event.target.checked) next.add(one.key)
                        else next.delete(one.key)
                        return next
                      })
                    }
                  />
                  {one.label}
                  <span className="text-muted-foreground font-mono">
                    {spec.key}.{one.key}
                  </span>
                  {inCard && !inCard.has(`${spec.key}.${one.key}`) && (
                    <span className="text-amber-700 dark:text-amber-500">이 카드엔 없음</span>
                  )}
                </label>
              ))}
            </div>
          )}
          {spec && spec.rows.length > 0 && (
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={withTable}
                onChange={(event) => setWithTable(event.target.checked)}
              />
              표 줄도 넣기 — {spec.rows.map((one) => one.label).join(' · ')}
              {spec.curve ? ' (점 곡선: x·y 로 정리)' : ' (있는 그대로)'}
            </label>
          )}
          {spec && (
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={guard} onChange={(event) => setGuard(event.target.checked)} />
              값이 없으면 이 묶음을 뺀다 (첫 값을 조건으로)
            </label>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            취소
          </Button>
          <Button onClick={add} disabled={!spec}>
            추가
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
