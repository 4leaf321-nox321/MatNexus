/**
 * 해석용 물성 정의 편집기 — **줄을 골라 쌓고, 옆에서 실제 덱을 본다.**
 *
 * 정의는 JSON 이지만 JSON 으로 적게 하지 않았다. 이 문법은 자유 형식이 아니라
 * **네 가지 줄**뿐이라, 고르는 편이 적는 편보다 틀릴 자리가 적다 — 그리고 덱에서
 * 틀린 자리는 솔버가 오류로 알려 주지 않는다.
 *
 * ## 미리보기가 절반이다
 *
 * 오른쪽은 **실제 카드 하나로 지금 정의를 그려 본 것**이다. 저장하고 나서 틀린
 * 것을 아는 것과 다르다 — 인풋 파일 정의가 이미 같은 자리를 갖고 있고(ADR 0006),
 * 덱 쪽에서 그것이 더 필요하다: 칸이 어긋나면 **다른 필드로 읽히고** 해석은 그대로
 * 돌아 그럴듯한 결과를 낸다.
 *
 * **못 냈어도 오류를 던지지 않는다.** 못 낸 이유가 응답 안에 있고, 그것을 보여
 * 주는 것이 미리보기의 일이다.
 */

import { useEffect, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, Plus, Search, Trash2, Upload } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { CardPickerDialog } from '@/modules/fitting/CardPickerDialog'
import { fittingApi } from '@/modules/fitting/api'
import type { DeckPreview, ExportProfile, PropertyCard } from '@/modules/fitting/api'
import {
  BLOCKS,
  FORMATS,
  LINE_KINDS,
  blank,
  fromDefinitionLine,
  fromScan,
  toDefinitionLine,
} from '@/modules/fitting/deckLines'
import type { DeckLine, FieldSpec, LineKind } from '@/modules/fitting/deckLines'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
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

export default function ExportProfileEditorPage() {
  const { key } = useParams<{ key: string }>()
  const navigate = useNavigate()
  const editing = Boolean(key)

  const [profileKey, setProfileKey] = useState(key ?? '')
  const [label, setLabel] = useState('')
  const [extension, setExtension] = useState('inp')
  const [describe, setDescribe] = useState('')
  const [lines, setLines] = useState<DeckLine[]>([blank('text')])
  const [error, setError] = useState<Error | null>(null)
  const [saving, setSaving] = useState(false)
  const [scanNotes, setScanNotes] = useState<string[]>([])

  // **실물 카드라야 뜻이 있다** — 지어낸 값으로는 「이 카드에는 밀도가 없다」
  // 같은 것이 안 드러난다.
  const cards = useResource(() => fittingApi.cards({ limit: 20 }), [])
  // 블록 이름을 사람이 읽는 말로. **화면이 `elastic`·`viscoelastic` 을 몰라야
  // 한다** — 그것이 새 물성을 확장으로 붙일 수 있는 이유다.
  const specs = useResource(() => fittingApi.blocks(), [])
  const [cardId, setCardId] = useState<string>('')
  const [preview, setPreview] = useState<DeckPreview | null>(null)
  // 최근 20장 밖의 카드를 찾을 때. **덱 정의를 만드는 일은 대개 「이 정의를
  // 설명하기 좋은 카드」 를 찾는 일이다** — 최근 스무 장에 그것이 있으리라는
  // 보장이 없다.
  const [picking, setPicking] = useState(false)
  // 찾아서 고른 카드는 최근 20장에 없을 수 있다 — 이름을 따로 들고 있는다.
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
    setLines(raw.map((one) => fromDefinitionLine(one as Record<string, unknown>)))
  }, [existing.data])

  useEffect(() => {
    if (cardId) return
    // **값이 가장 많은 카드로 시작한다.** 목록 첫 장을 잡으면 그것이 탄성만 든
    // 카드일 수 있고, 그러면 미리보기가 계속 「값이 없다」 를 내는데 사람은
    // 정의를 의심한다 — 실제로 할 일은 다른 카드를 고르는 것이다.
    const richest = [...(cards.data?.items ?? [])].sort(
      (a, b) => Object.keys(b.blocks ?? {}).length - Object.keys(a.blocks ?? {}).length
    )[0]
    if (richest) setCardId(richest.id)
  }, [cards.data, cardId])

  const definition = useMemo(
    () => ({
      extension,
      describe: describe || '해석용 물성 정의',
      lines: lines.map(toDefinitionLine),
    }),
    [extension, describe, lines]
  )

  // **적는 대로 그려 본다.** 저장을 눌러야 알게 하면 그때는 이미 고칠 마음이 식는다.
  useEffect(() => {
    if (!cardId) return
    let alive = true
    const timer = setTimeout(() => {
      void fittingApi
        .previewDeck({ ...definition, label: label || '덱' }, cardId)
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
            })
          }
        })
    }, 400)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [definition, cardId, label])

  /**
   * 예제 덱을 읽어 줄을 채운다.
   *
   * **덱을 붙이려는 사람에게는 대개 그 솔버의 덱 파일이 이미 있다** — 해석을
   * 돌려 본 사람이니까. 인풋 파일 정의가 같은 문제를 이미 풀었고(ADR 0006),
   * 여기도 같은 선이다: 구조는 서버가 읽고 **「이 값이 무엇인가」 만 사람이 정한다.**
   */
  async function readExample(file: File) {
    setError(null)
    try {
      const found = await fittingApi.scanDeck(await file.text(), cardId || undefined)
      setLines(fromScan(found))
      setScanNotes(found.notes ?? [])
      // 확장자도 가져온다 — 올린 파일이 그 솔버의 것이므로 대개 맞다.
      const dot = file.name.lastIndexOf('.')
      if (dot > 0) setExtension(file.name.slice(dot + 1))
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('예제 덱을 읽지 못했습니다.'))
    }
  }

  /**
   * 카드 한 장을 드롭다운에 적는 말.
   *
   * **`label` 만으로는 못 고른다.** 카드 이름은 사람이 지은 것이라 「내보내기
   * 시험」 같은 말이 들어 있고, 그것만 봐서는 어느 재료의 무슨 물성인지 알 수
   * 없다 — 그런데 미리보기 카드를 고르는 일은 곧 **「이 정의가 쓰는 값이 그
   * 카드에 있나」** 를 고르는 일이다.
   */
  function describeCard(one: PropertyCard): string {
    const kinds = Object.keys(one.blocks ?? {})
      .map((key) => specs.data?.find((spec) => spec.key === key)?.label ?? key)
      .join(' · ')
    const where = [one.material_name, one.orientation].filter(Boolean).join(' · ')
    return [where, kinds || '값 없음'].filter(Boolean).join(' — ')
  }

  function patch(index: number, change: Partial<DeckLine>) {
    setLines((old) => old.map((one, at) => (at === index ? { ...one, ...change } : one)))
  }

  function patchField(index: number, at: number, change: Partial<FieldSpec>) {
    setLines((old) =>
      old.map((one, i) =>
        i === index
          ? {
              ...one,
              fields: (one.fields ?? []).map((field, j) =>
                j === at ? { ...field, ...change } : field
              ),
            }
          : one
      )
    )
  }

  function move(index: number, by: number) {
    // **차례가 곧 덱이다.** 키워드 순서가 바뀌면 솔버가 다르게 읽는다.
    setLines((old) => {
      const to = index + by
      if (to < 0 || to >= old.length) return old
      const next = [...old]
      const [taken] = next.splice(index, 1)
      next.splice(to, 0, taken)
      return next
    })
  }

  async function save() {
    setError(null)
    setSaving(true)
    try {
      if (editing && key) {
        await fittingApi.saveExportProfile(key, { label, definition, is_active: true })
      } else {
        await fittingApi.createExportProfile({
          key: profileKey,
          label,
          definition,
          is_active: true,
        })
      }
      navigate('/settings/export-profiles')
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <PageHeader
        sticky
        title={editing ? `해석용 물성 정의 · ${key}` : '해석용 물성 정의 만들기'}
        description="줄을 골라 쌓습니다. 오른쪽은 고른 카드로 지금 정의를 실제로 그려 본 것입니다 — 저장하기 전에 봅니다."
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

      <div className="grid gap-6 xl:grid-cols-[minmax(0,6fr)_minmax(0,4fr)]">
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
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
          </div>

          {/* **빈 폼에서 시작하지 않게.** 파일 하나면 줄·칸 폭·이름 제안까지
              채워진다 — 남는 일은 「이 값이 무엇인가」 를 정하는 것뿐이다. */}
          <div className="bg-muted/40 rounded-md border border-dashed p-3">
            <div className="flex flex-wrap items-center gap-2">
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
              <span className="text-muted-foreground text-xs">
                그 솔버의 덱 파일을 올리면 줄과 칸 폭을 읽어 초안을 만듭니다.
                {cardId ? ' 고른 카드의 값과 같은 숫자에는 이름도 붙입니다.' : ''}
              </span>
            </div>

            {/* **짐작한 자리를 숨기지 않는다.** 표로 묶은 줄·고정폭으로 본 줄이
                어디인지 말해야 사람이 확인할 데를 안다. */}
            {scanNotes.length ? (
              <ul className="text-muted-foreground mt-2 space-y-1 text-xs">
                {scanNotes.map((one, at) => (
                  <li key={at}>· {one}</li>
                ))}
              </ul>
            ) : null}
          </div>

          <div className="space-y-2">
            {lines.map((line, index) => (
              <div key={index} className="rounded-md border p-3">
                <div className="mb-2 flex items-center gap-2">
                  <span className="text-muted-foreground w-6 text-xs">{index + 1}</span>
                  <Select
                    value={line.kind}
                    onValueChange={(value) => patch(index, blank(value as LineKind))}
                  >
                    <SelectTrigger className="h-8 w-28" aria-label={`${index + 1}번 줄 종류`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {LINE_KINDS.map((one) => (
                        <SelectItem key={one.key} value={one.key}>
                          {one.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {line.kind === 'text' ? (
                    <Input
                      className="h-8 flex-1 font-mono text-xs"
                      value={line.text ?? ''}
                      onChange={(event) => patch(index, { text: event.target.value })}
                      placeholder="*MATERIAL, NAME={name}"
                      aria-label={`${index + 1}번 줄 글자`}
                    />
                  ) : null}

                  {line.kind === 'block' ? (
                    <Select
                      value={line.block ?? 'header'}
                      onValueChange={(value) => patch(index, { block: value })}
                    >
                      <SelectTrigger className="h-8 flex-1" aria-label={`${index + 1}번 줄 묶음`}>
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
                  ) : null}

                  {line.kind === 'rows' ? (
                    <>
                      <Input
                        className="h-8 w-32 font-mono text-xs"
                        value={line.rows ?? ''}
                        onChange={(event) => patch(index, { rows: event.target.value })}
                        placeholder="table"
                        aria-label={`${index + 1}번 줄 표 이름`}
                      />
                      {/* **x·y 를 주면 점 표로 본다** — 중복을 묶고 단조성을 본다.
                          안 주면 있는 그대로 쓴다(Prony 는 점이 아니다). */}
                      <Input
                        className="h-8 w-28 font-mono text-xs"
                        value={line.x ?? ''}
                        onChange={(event) => patch(index, { x: event.target.value })}
                        placeholder="x (선택)"
                        aria-label={`${index + 1}번 줄 x 열`}
                      />
                      <Input
                        className="h-8 w-28 font-mono text-xs"
                        value={line.y ?? ''}
                        onChange={(event) => patch(index, { y: event.target.value })}
                        placeholder="y (선택)"
                        aria-label={`${index + 1}번 줄 y 열`}
                      />
                    </>
                  ) : null}

                  <span className="ml-auto flex gap-1">
                    <Button variant="ghost" size="icon" title="위로" onClick={() => move(index, -1)}>
                      <ArrowUp className="size-4" />
                    </Button>
                    <Button variant="ghost" size="icon" title="아래로" onClick={() => move(index, 1)}>
                      <ArrowDown className="size-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      title="줄 지우기"
                      onClick={() => setLines((old) => old.filter((_, at) => at !== index))}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </span>
                </div>

                {line.kind === 'fields' || line.kind === 'rows' ? (
                  <div className="space-y-1.5 pl-8">
                    {/* **값 앞에 글자가 붙는 솔버가 있다.** ANSYS 는
                        `MP,EX,1,2.1E5`, Nastran 벌크는 `MAT1` 이 첫 칸을
                        차지한다 — 못 적으면 그 솔버는 아예 못 붙인다. */}
                    <Input
                      className="h-8 font-mono text-xs"
                      value={line.prefix ?? ''}
                      onChange={(event) => patch(index, { prefix: event.target.value })}
                      placeholder="값 앞에 붙는 글자 (선택) — MP,EX,"
                      aria-label={`${index + 1}번 줄 접두`}
                    />
                    {(line.fields ?? []).map((field, at) => (
                      <div key={at} className="flex items-center gap-2">
                        <Input
                          className="h-8 flex-1 font-mono text-xs"
                          value={field.const ?? field.value ?? ''}
                          onChange={(event) =>
                            patchField(index, at, {
                              [field.const !== undefined ? 'const' : 'value']: event.target.value,
                            } as Partial<FieldSpec>)
                          }
                          placeholder={line.kind === 'rows' ? 'true_stress' : 'elastic.density'}
                          aria-label={`${index + 1}번 줄 ${at + 1}번 칸`}
                        />
                        <Select
                          value={
                            Array.isArray(field.format) ? field.format[0] : (field.format ?? 'free')
                          }
                          onValueChange={(value) =>
                            patchField(index, at, {
                              // **고정폭은 폭·자릿수가 함께 있어야 뜻이 선다.**
                              // 이름만 보내면 서버가 폭을 못 읽는다. 맞춤만 바꿀
                              // 때는 이미 잰 폭을 지키고, 없으면 20칸에서 시작한다.
                              format: value.startsWith('fixed')
                                ? [
                                    value,
                                    Array.isArray(field.format) ? field.format[1] : 20,
                                    Array.isArray(field.format) ? field.format[2] : 9,
                                  ]
                                : value,
                            })
                          }
                        >
                          <SelectTrigger
                            className="h-8 w-52"
                            aria-label={`${index + 1}번 줄 ${at + 1}번 칸 형식`}
                          >
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
                        <Button
                          variant="ghost"
                          size="icon"
                          title="칸 지우기"
                          onClick={() =>
                            patch(index, {
                              fields: (line.fields ?? []).filter((_, j) => j !== at),
                            })
                          }
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    ))}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        patch(index, {
                          fields: [...(line.fields ?? []), { value: '', format: 'free' }],
                        })
                      }
                    >
                      <Plus className="size-3" />칸 추가
                    </Button>
                  </div>
                ) : null}

                {/* **있으면 넣고 없으면 빼기.** 밀도가 그렇다 — 그리고 뺐다는
                    사실을 덱 주석과 사람에게 남긴다. */}
                <div className="mt-2 grid gap-2 pl-8 sm:grid-cols-2">
                  <Input
                    className="h-8 font-mono text-xs"
                    value={line.when ?? ''}
                    onChange={(event) => patch(index, { when: event.target.value })}
                    placeholder="조건 (elastic.density / missing:elastic.density)"
                    aria-label={`${index + 1}번 줄 조건`}
                  />
                  <Input
                    className="h-8 text-xs"
                    value={line.note ?? ''}
                    onChange={(event) => patch(index, { note: event.target.value })}
                    placeholder="사람에게 남길 말 (선택)"
                    aria-label={`${index + 1}번 줄 안내`}
                  />
                </div>
              </div>
            ))}

            <div className="flex flex-wrap gap-2">
              {LINE_KINDS.map((one) => (
                <Button
                  key={one.key}
                  variant="outline"
                  size="sm"
                  title={one.hint}
                  onClick={() => setLines((old) => [...old, blank(one.key)])}
                >
                  <Plus className="size-3" />
                  {one.label} 줄
                </Button>
              ))}
            </div>
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
                  <SelectValue placeholder="카드를 고르세요">
                    {/* 찾아서 고른 카드는 아래 목록에 없을 수 있다. 그때 빈칸이
                        뜨면 무엇을 고른 것인지 화면에 안 남는다. */}
                    {pickedName ?? undefined}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {(cards.data?.items ?? []).map((one) => (
                    <SelectItem key={one.id} value={one.id}>
                      {describeCard(one)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="sm"
                className="h-8"
                onClick={() => setPicking(true)}
              >
                <Search className="size-4" />
                상세
              </Button>
            </div>
            <p className="text-muted-foreground text-xs">
              {/* **왜 고르는지를 적어 둔다.** 이 자리가 무엇을 하는 자리인지
                  화면에 없으면 아무거나 고르고, 그러면 미리보기가 계속 「값이
                  없다」 를 내는데 정의를 의심하게 된다. */}
              이 카드의 값으로 덱을 그려 봅니다. 정의가 쓰는 값이 든 카드를 고르세요 —
              없는 값은 아래에 「이 카드에 없는 값」 으로 뜹니다.
            </p>
            {cards.data && cards.data.items.length === 0 ? (
              <p className="text-muted-foreground rounded-md border border-dashed p-3 text-xs">
                아직 물성 카드가 없습니다. 카드를 하나 만들면 여기서 덱을 그려 볼 수
                있습니다 — 그 전에는 정의가 맞는지 확인할 길이 없습니다.
              </p>
            ) : null}
          </div>

          {preview?.error ? (
            <p className="border-destructive/40 bg-destructive/5 text-destructive rounded-md border p-3 text-sm">
              {preview.error}
            </p>
          ) : null}

          {/* **정의가 틀린 것과 카드가 빈 것은 다르다.** 구별이 안 되면 멀쩡한
              정의를 고치며 시간을 버린다 — 할 일은 다른 카드를 고르는 것이다. */}
          {preview?.missing?.length ? (
            <p className="text-muted-foreground rounded-md border border-dashed p-3 text-sm">
              이 카드에 없는 값: {preview.missing.join(', ')} — 정의가 아니라 카드 쪽입니다. 다른
              카드로 봐 주세요.
            </p>
          ) : null}

          <pre className="bg-muted max-h-[60vh] overflow-auto rounded-md p-3 font-mono text-xs">
            {preview?.text ?? '카드를 고르면 여기에 덱이 나옵니다.'}
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
