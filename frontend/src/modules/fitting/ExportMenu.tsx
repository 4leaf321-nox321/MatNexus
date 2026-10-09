/**
 * 카드 하나를 솔버 덱으로 내보내는 창.
 *
 * **두 화면이 같은 것을 쓴다** — 재료 상세의 'CAE 카드' 탭과 전역 카드 목록.
 * 각자 만들면 한쪽만 고쳐지는 날이 오고, 그때 같은 카드가 화면에 따라 다른
 * 형식 목록을 갖는다.
 *
 * ## 고르고, 보고, 받는다 (2026-10-04)
 *
 * 전에는 메뉴에서 형식을 누르자마자 파일이 내려왔다. 요청: 「내보내기 창을 큰 모달로 —
 * 툴 목록을 왼쪽에, 오른쪽에는 카드의 어느 위치에 어떤 변수가 들어가는지와 그 예시가
 * 어떻게 나오는지」. 고정폭 칸이 하나 밀리면 솔버는 다른 값을 **조용히** 읽는다 — 받기 전에
 * 「탄성계수가 저 칸으로 간다」 를 볼 자리가 있어야 한다.
 *
 *     위        덱의 단위계 — 형식보다 먼저 한 번 고른다
 *     툴 열     「전체」 · 솔버마다(낼 수 있는 수 / 전체 수) — 2026-10-04 둘째 지적으로 갈랐다
 *     카드 열   고른 툴의 솔버 카드(형식) · 짝 카드 · 못 내는 형식(까닭과 함께). 「전체」 면 전부
 *     오른쪽    칸 배치(값 → 줄 · 칸) · 덱 미리보기(그 자리를 칠한다) · 내려받기
 *
 * 배치는 서버가 **실제로 내려받을 덱**을 그대로 짚는다(`GET …/export/layout` — 값을 하나씩
 * 흔들어 바뀐 자리를 찾는다). 여러 값에서 셈한 칸(G = E/2(1+ν))은 그 값들이 함께 짚는다.
 *
 * ## 낼 수 있는지 서버가 판정한다
 *
 * 카드가 `available_formats` 를 들고 온다. **누르기 전에 알려 준다** — 내려받기를 누른 뒤에
 * 「푸아송비가 없습니다」 를 보는 것은 늦다.
 *
 * ## 단위계는 형식보다 위에 있다
 *
 * 형식마다 두 벌로 늘리면 목록이 두 배가 되고, 「형식을 고르다가 단위계를 잘못 고르는」
 * 실수를 만든다. 단위계를 **먼저 한 번** 고르고, 그 아래에서 형식을 고른다. 고른 계는 항상
 * 화면에 떠 있다. **단위가 정해진 형식**(AEDT · CST · Flotherm · Zemax — `fixed_units`)은 고른
 * 계와 상관없이 그 계로 나간다 — 형식 줄에 그 사실을 적는다.
 */

import { useState } from 'react'
import { ChevronDown, ChevronRight, Download, FileDown } from 'lucide-react'

import { fittingApi } from '@/modules/fitting/api'
import { groupBySolver, solverOf } from '@/modules/fitting/formatGroups'
import type {
  DeckLayout,
  DeckLayoutValue,
  ExportFormat,
  PropertyCard,
  UnitSystem,
} from '@/modules/fitting/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { useResource } from '@/shared/hooks/useResource'

/** 툴 열의 「전체」 — 솔버 이름과 겹치지 않는 값. */
const ALL = '__all__'

/** 고른 형식 — 짝 카드와 합쳐 내는 것이면 그 짝의 id 가 함께 든다. */
interface Choice {
  format: ExportFormat
  blocked: boolean
  withCard?: string
}

export function ExportMenu({
  card,
  formats,
  onError,
  siblings = [],
}: {
  card: PropertyCard
  formats: ExportFormat[]
  onError: (error: Error) => void
  /** 같은 재료의 다른 카드 — **짝 카드**로 고를 수 있다(ADR 0037). 이방성(r값) 카드는 혼자서는
   *  Hill 형식을 못 낸다: 경화 곡선·탄성이 MD 카드에 있다. 카드를 합쳐 새로 만들지 않고 내보낼
   *  때만 합친다. */
  siblings?: PropertyCard[]
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <FileDown className="size-3.5" />
        내보내기
      </Button>
      {/* **열 때만 세운다** — 목록에 카드가 수십 장이면 창마다 단위계를 미리 묻게 된다. */}
      {open ? (
        <ExportDialog
          card={card}
          formats={formats}
          siblings={siblings}
          onError={onError}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  )
}

function ExportDialog({
  card,
  formats,
  siblings,
  onError,
  onClose,
}: {
  card: PropertyCard
  formats: ExportFormat[]
  siblings: PropertyCard[]
  onError: (error: Error) => void
  onClose: () => void
}) {
  const systems = useResource(() => fittingApi.unitSystems(), [])
  const [chosen, setChosen] = useState<string | null>(null)
  const [choice, setChoice] = useState<Choice | null>(null)
  const [showBlocked, setShowBlocked] = useState(false)
  const [pair, setPair] = useState<{ card: PropertyCard; keys: string[] } | null>(null)
  // **툴을 먼저 고른다**(2026-10-04 둘째 지적) — 솔버 × 물성 모델로 형식이 쉰 개 넘게 한 열에
  // 서 있으면 찾는 데 시간이 든다. 「전체」 면 지금처럼 전부.
  const [tool, setTool] = useState<string>(ALL)
  const systemList = systems.data ?? []
  // 고르기 전에는 서버가 기본이라고 말한 것. **화면이 'si' 를 적어 두지 않는다.**
  const system =
    systemList.find((one) => one.key === chosen) ??
    systemList.find((one) => one.is_default) ??
    systemList[0] ??
    null

  const opens = (one: ExportFormat) => card.available_formats.includes(one.key)
  const inTool = (one: ExportFormat) => tool === ALL || solverOf(one.label) === tool
  const available = formats.filter((one) => opens(one) && inTool(one))
  const blocked = formats.filter((one) => !opens(one) && inTool(one))
  const partners = siblings.filter(
    (one) => one.id !== card.id && one.material_id === card.material_id
  )
  // 툴 열 — **못 내는 형식뿐인 툴도 선다.** 빼면 「이 툴은 없나」 로 읽힌다.
  const tools = groupBySolver(formats).map((group) => ({
    solver: group.solver,
    total: group.items.length,
    open: group.items.filter(opens).length,
  }))

  function selected(format: ExportFormat, withCard?: string): boolean {
    return choice?.format.key === format.key && choice.withCard === withCard
  }

  return (
    <Dialog open onOpenChange={(next) => (next ? null : onClose())}>
      {/* **가로로 넓게** — 열 셋에 덱 미리보기까지 서야 한다. 고정폭 덱은 한 줄이 80칸이다. */}
      <DialogContent className="flex h-[88vh] max-h-[88vh] flex-col sm:max-w-[min(96vw,1800px)]">
        <DialogHeader>
          <DialogTitle>내보내기 — {card.label}</DialogTitle>
          <DialogDescription>
            툴과 솔버 카드를 고르면 덱의 어느 자리에 카드의 어느 값이 가는지와 덱 미리보기가
            섭니다. 확인한 뒤 내려받으세요.
          </DialogDescription>
        </DialogHeader>

        <section aria-label="덱의 단위계" className="flex flex-wrap items-center gap-2">
          <p className="text-xs font-medium">덱의 단위계</p>
          <div className="flex flex-wrap gap-1">
            {systemList.map((one) => (
              <button
                key={one.key}
                type="button"
                aria-pressed={system?.key === one.key}
                className={`rounded-md border px-2 py-1 text-xs ${
                  system?.key === one.key ? 'bg-primary text-primary-foreground' : ''
                }`}
                onClick={() => setChosen(one.key)}
              >
                {one.label}
              </button>
            ))}
          </div>
          {/* **덱에 무엇이라 적히는지 그대로 보인다.** 받는 사람이 파일에서 읽을 줄과 같은
              글자라, 나중에 대조할 수 있다. */}
          <p className="text-muted-foreground font-mono text-xs">
            {system ? system.declaration : '단위계를 읽는 중…'}
          </p>
          <p className="text-muted-foreground w-full text-xs">
            값이 이 계로 환산돼 나가고, 덱 머리와 <b>파일 이름</b>에 적힙니다. 단위계가 섞인
            덱은 조용히 1000배 틀린 답을 냅니다.
          </p>
        </section>

        <div className="grid min-h-0 flex-1 grid-cols-[10rem_19rem_minmax(0,1fr)] gap-4">
          <nav aria-label="툴" className="min-h-0 overflow-y-auto border-r pr-2">
            <p className="text-muted-foreground px-2 pb-1 text-xs font-medium">툴</p>
            <ToolButton
              label="전체"
              open={formats.filter(opens).length}
              total={formats.length}
              active={tool === ALL}
              onPick={() => setTool(ALL)}
            />
            {tools.map((one) => (
              <ToolButton
                key={one.solver}
                label={one.solver}
                open={one.open}
                total={one.total}
                active={tool === one.solver}
                onPick={() => setTool(one.solver)}
              />
            ))}
          </nav>

          <nav aria-label="솔버 카드" className="min-h-0 overflow-y-auto border-r pr-2">
            <p className="text-muted-foreground px-2 pb-1 text-xs font-medium">솔버 카드</p>
            {/* **낼 수 있는 것을 먼저.** 「전체」 면 솔버 제목 아래 묶는다. 못 내는 것은 접어
                둔다 — 없애지 않는다: 「왜 못 내나」 가 그 자리에 있다. */}
            {groupBySolver(available).map((group) => (
              <div key={group.solver} className="mb-2">
                {tool === ALL ? (
                  <p className="text-muted-foreground px-2 pt-1 text-xs font-medium">
                    {group.solver}
                  </p>
                ) : null}
                {group.items.map((format) => (
                  <FormatButton
                    key={format.key}
                    format={format}
                    blocked={false}
                    active={selected(format)}
                    onPick={() => setChoice({ format, blocked: false })}
                  />
                ))}
              </div>
            ))}
            {available.length === 0 ? (
              <p className="text-muted-foreground px-2 py-1.5 text-xs">
                {tool === ALL
                  ? '이 카드로 낼 수 있는 형식이 아직 없습니다.'
                  : `이 카드로 ${tool} 에 낼 수 있는 형식이 없습니다.`}
              </p>
            ) : null}

            {blocked.length > 0 && partners.length > 0 ? (
              <div className="mt-2 border-t px-2 pt-2">
                <p className="text-xs font-medium">짝 카드와 합쳐 내기</p>
                <p className="text-muted-foreground mt-0.5 text-xs">
                  이 카드에 없는 것(경화 곡선·탄성)을 같은 재료의 다른 카드에서 가져옵니다 —
                  이방성 카드는 <b>압연 방향(MD)</b> 카드를 고르세요.
                </p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {partners.map((one) => (
                    <button
                      key={one.id}
                      type="button"
                      aria-pressed={pair?.card.id === one.id}
                      className={`rounded-md border px-2 py-0.5 text-xs ${
                        pair?.card.id === one.id ? 'bg-primary text-primary-foreground' : ''
                      }`}
                      onClick={() =>
                        fittingApi
                          .pairedFormats(card.id, one.id)
                          .then((found) => setPair({ card: one, keys: found.available_formats }))
                          .catch((caught: unknown) =>
                            onError(
                              caught instanceof Error
                                ? caught
                                : new Error('짝 카드를 못 읽었습니다.')
                            )
                          )
                      }
                    >
                      {one.label}
                      {one.orientation ? ` · ${one.orientation}` : ''}
                    </button>
                  ))}
                </div>
                {pair && pair.keys.length === 0 ? (
                  <p className="text-muted-foreground mt-1.5 text-xs">
                    이 짝으로 새로 낼 수 있는 형식이 없습니다.
                  </p>
                ) : null}
                {pair
                  ? formats
                      .filter((one) => pair.keys.includes(one.key) && inTool(one))
                      .map((format) => (
                        <FormatButton
                          key={`pair-${format.key}`}
                          format={format}
                          blocked={false}
                          active={selected(format, pair.card.id)}
                          onPick={() =>
                            setChoice({ format, blocked: false, withCard: pair.card.id })
                          }
                        />
                      ))
                  : null}
              </div>
            ) : null}

            {blocked.length > 0 ? (
              <div className="mt-2 border-t pt-1">
                <button
                  type="button"
                  className="text-muted-foreground flex w-full items-center gap-1 px-2 py-1.5 text-left text-xs"
                  onClick={() => setShowBlocked((shown) => !shown)}
                >
                  {showBlocked ? (
                    <ChevronDown className="size-3.5" />
                  ) : (
                    <ChevronRight className="size-3.5" />
                  )}
                  이 카드로는 못 내는 형식 {blocked.length}개
                </button>
                {showBlocked
                  ? blocked.map((format) => (
                      <FormatButton
                        key={format.key}
                        format={format}
                        blocked
                        active={selected(format)}
                        onPick={() => setChoice({ format, blocked: true })}
                      />
                    ))
                  : null}
              </div>
            ) : null}
          </nav>

          <div className="min-h-0 overflow-y-auto">
            {choice === null ? (
              <p className="text-muted-foreground p-6 text-sm">
                왼쪽에서 툴과 솔버 카드를 고르세요 — 덱의 어느 자리에 무엇이 가는지 여기 섭니다.
              </p>
            ) : choice.blocked ? (
              <BlockedPanel format={choice.format} />
            ) : system === null ? (
              <p className="text-muted-foreground p-6 text-sm">단위계를 읽는 중…</p>
            ) : (
              // **형식 · 계 · 짝이 바뀌면 새로 세운다** — 앞 형식의 배치가 다음 형식이 올
              // 때까지 남아 있으면 「이 칸에 이 값」 이 엉뚱한 덱을 가리킨다.
              <LayoutPanel
                key={`${choice.format.key}|${system.key}|${choice.withCard ?? ''}`}
                card={card}
                choice={choice}
                system={system}
                onError={onError}
              />
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function ToolButton({
  label,
  open,
  total,
  active,
  onPick,
}: {
  label: string
  open: number
  total: number
  active: boolean
  onPick: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={`flex w-full items-baseline gap-2 rounded-md px-2 py-1.5 text-left text-sm ${
        active ? 'bg-accent' : 'hover:bg-muted'
      } ${open === 0 ? 'opacity-70' : ''}`}
      onClick={onPick}
    >
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {/* 낼 수 있는 수 / 전체 수 — 고르기 전에 「이 툴로 몇 개나 나오나」. */}
      <span className="text-muted-foreground shrink-0 text-xs" title="이 카드로 낼 수 있는 형식 / 전체">
        {open}/{total}
      </span>
    </button>
  )
}

function FormatButton({
  format,
  blocked,
  active,
  onPick,
}: {
  format: ExportFormat
  blocked: boolean
  active: boolean
  onPick: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      data-format-available={blocked ? 'false' : 'true'}
      className={`w-full rounded-md px-2 py-1.5 text-left ${
        active ? 'bg-accent' : 'hover:bg-muted'
      } ${blocked ? 'opacity-70' : ''}`}
      onClick={onPick}
    >
      <p className="text-sm">{format.label}</p>
      <p className="text-muted-foreground text-xs">
        {blocked
          ? `${format.requires.join('·')} 가 있어야 냅니다. 카드에 아직 없습니다.`
          : format.describe}
      </p>
      {format.fixed_units && !blocked ? (
        <p className="text-muted-foreground text-xs">
          단위는 형식이 정합니다 — 고른 계와 상관없이 <b>{format.fixed_units.toUpperCase()}</b>
          로 나갑니다.
        </p>
      ) : null}
    </button>
  )
}

function BlockedPanel({ format }: { format: ExportFormat }) {
  return (
    <div className="space-y-2 p-2">
      <h3 className="font-medium">{format.label}</h3>
      <p className="text-sm">{format.describe}</p>
      <p className="text-destructive text-sm" role="alert">
        이 카드로는 못 냅니다 — {format.requires.join('·')} 가 있어야 하는데 카드에 아직
        없습니다. 카드를 만들 때 넣거나, 재료에 적어 두면 다음 카드가 물려받습니다.
      </p>
    </div>
  )
}

/** 덱의 숫자 — 덱에 적힌 계 그대로. 아주 크거나 작으면 지수로. */
function shownNumber(value: number): string {
  const size = Math.abs(value)
  if (size !== 0 && (size >= 1e6 || size < 1e-3)) return value.toExponential(4)
  return String(Number(value.toPrecision(6)))
}

/** 자리를 한 줄로 — 「12줄 11–20칸」 · 열이면 「20–70줄」. 줄 · 칸은 1 부터. */
function where(value: DeckLayoutValue): string {
  const spans = value.spans
  if (spans.length === 0) return '—'
  if (value.column) {
    const lines = spans.map((one) => one.line + 1)
    return `${Math.min(...lines)}–${Math.max(...lines)}줄 (${spans.length}곳)`
  }
  const first = spans[0]
  const head = `${first.line + 1}줄 ${first.start + 1}–${first.end}칸`
  return spans.length > 1 ? `${head} 외 ${spans.length - 1}곳` : head
}

function LayoutPanel({
  card,
  choice,
  system,
  onError,
}: {
  card: PropertyCard
  choice: Choice
  system: UnitSystem
  onError: (error: Error) => void
}) {
  // **파단 칸 켜기**(ADR 0059 후속) — 카드가 아니라 이 덱 한 벌의 결정이다. 고를 수 있는지는
  // 서버가 켜고 끈 덱을 그려 보고 알린다(`fail_option`) — 형식 이름을 여기 외우지 않는다.
  const [fail, setFail] = useState(false)
  const layout = useResource(
    () => fittingApi.layout(card.id, choice.format, system, choice.withCard, fail),
    [fail]
  )
  const [focus, setFocus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const data = layout.data
  const format = choice.format
  // 미리보기가 고른 것을 아직 못 따라왔으면 받지 않는다 — 미리 본 덱과 받은 덱이 갈린다.
  const behind = layout.loading || (data !== null && Boolean(data.fail_from_elongation) !== fail)

  function download() {
    setBusy(true)
    fittingApi
      .download(card.id, format, card.label, system, choice.withCard, fail)
      .catch((caught: unknown) =>
        onError(caught instanceof Error ? caught : new Error('내보내지 못했습니다.'))
      )
      .finally(() => setBusy(false))
  }

  // 이름 → 사람이 읽는 이름. 「함께 셈한 값」 을 이 이름으로 적는다.
  const names = new Map((data?.values ?? []).map((one) => [one.name, one.label]))

  return (
    <div className="space-y-4 p-1">
      <header className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="font-medium">{format.label}</h3>
          <p className="text-muted-foreground text-xs">{format.describe}</p>
          {format.fixed_units ? (
            <p className="text-muted-foreground text-xs">
              단위는 형식이 정합니다 — 고른 계와 상관없이{' '}
              <b>{format.fixed_units.toUpperCase()}</b>로 나갑니다.
            </p>
          ) : null}
          {data?.ok ? <p className="font-mono text-xs">{data.filename}</p> : null}
        </div>
        <Button size="sm" disabled={busy || behind || !data?.ok} onClick={download}>
          <Download className="size-3.5" />
          내려받기
        </Button>
      </header>

      {data?.fail_option || fail ? (
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={fail}
            onChange={(event) => setFail(event.target.checked)}
          />
          <span>
            추정 파단 변형률을 파단 칸에 넣기
            <span className="text-muted-foreground block text-xs">
              파단 연신율 A 로 ln(1+A) 를 추정해 FAIL · Eps_p_max 칸에 적습니다 — 그 변형률에서
              요소가 지워집니다. 게이지 길이 · 요소 크기에 따라 맞는 값이 달라서 기본은 덱 주석으로만
              적습니다.
            </span>
          </span>
        </label>
      ) : null}

      <ErrorNotice error={layout.error} />
      {layout.loading && !data ? (
        <p className="text-muted-foreground text-sm">덱을 그려 칸을 짚는 중…</p>
      ) : null}
      {data && !data.ok ? (
        <p className="text-destructive text-sm" role="alert">
          {data.error}
        </p>
      ) : null}

      {data?.ok ? (
        <>
          <section aria-label="칸 배치" className="space-y-1">
            <h4 className="text-sm font-medium">칸 배치 — 카드의 어느 값이 덱의 어디로 가나</h4>
            <p className="text-muted-foreground text-xs">
              줄을 누르면 아래 미리보기에서 그 자리를 짙게 칠합니다. 「함께 셈한 칸」 은 그
              값들로 계산해 적는 자리입니다(예: E · ν 에서 G).
            </p>
            <Table className="text-xs" aria-label="칸 배치">
              <TableHeader>
                <TableRow>
                  <TableHead>값</TableHead>
                  <TableHead className="text-right">덱에 적히는 값</TableHead>
                  <TableHead>자리</TableHead>
                  <TableHead>비고</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.values.map((one) => {
                  const shared = [
                    ...new Set(one.spans.flatMap((span) => span.shared_with ?? [])),
                  ].map((name) => names.get(name) ?? name)
                  return (
                    <TableRow
                      key={one.name}
                      aria-selected={focus === one.name}
                      className={`cursor-pointer ${focus === one.name ? 'bg-accent' : ''}`}
                      onClick={() => setFocus(focus === one.name ? null : one.name)}
                    >
                      <TableCell>
                        {one.block_label} · {one.label}
                        <span className="text-muted-foreground font-mono"> {one.key}</span>
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {one.value === null || one.value === undefined
                          ? '—'
                          : shownNumber(one.value)}
                        {one.unit ? ` ${one.unit}` : ''}
                        {one.column ? ` 외 ${Math.max(0, (one.rows ?? 0) - 1)}행` : ''}
                      </TableCell>
                      <TableCell>{where(one)}</TableCell>
                      <TableCell>
                        {shared.length > 0 ? `함께 셈한 칸: ${shared.join(' · ')}` : ''}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
            {data.unused.length > 0 ? (
              <p className="text-muted-foreground text-xs">
                이 형식이 안 쓰는 값:{' '}
                {data.unused.map((one) => `${one.block_label} · ${one.label}`).join(', ')}
              </p>
            ) : null}
            {data.failed.length > 0 ? (
              <p className="text-muted-foreground text-xs">
                자리를 못 짚은 값(값을 바꿔 보면 덱이 안 나온다):{' '}
                {data.failed.map((one) => `${one.block_label} · ${one.label}`).join(', ')}
              </p>
            ) : null}
          </section>

          {data.notes.length > 0 ? (
            <section aria-label="덱 각주" className="space-y-1">
              <h4 className="text-sm font-medium">내보내면서 한 일</h4>
              <ul className="list-disc pl-5 text-xs">
                {data.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <section aria-label="덱 미리보기" className="space-y-1">
            <h4 className="text-sm font-medium">
              미리보기 — 내려받을 덱 그대로
              {data.truncated
                ? ` (전체 ${data.line_count.toLocaleString('ko-KR')}줄 중 앞부분)`
                : ''}
            </h4>
            <DeckPreview layout={data} focus={focus} />
          </section>
        </>
      ) : null}
    </div>
  )
}

/** 줄마다 칠할 자리 — `[시작, 끝, 그 자리의 값 이름들]`. 겹치면 이름을 합친다. */
function segmentsOf(layout: DeckLayout): Map<number, [number, number, string[]][]> {
  const found = new Map<number, [number, number, string[]][]>()
  for (const value of layout.values) {
    for (const span of value.spans) {
      const list = found.get(span.line) ?? []
      const same = list.find(([start, end]) => start === span.start && end === span.end)
      if (same) same[2].push(value.name)
      else list.push([span.start, span.end, [value.name]])
      found.set(span.line, list)
    }
  }
  for (const list of found.values()) list.sort((a, b) => a[0] - b[0])
  return found
}

function DeckPreview({ layout, focus }: { layout: DeckLayout; focus: string | null }) {
  const lines = layout.text.split('\n')
  const marks = segmentsOf(layout)
  const labels = new Map(layout.values.map((one) => [one.name, `${one.block_label} · ${one.label}`]))
  const width = String(lines.length).length

  return (
    <pre
      aria-label="덱 본문"
      className="bg-muted/40 max-h-[60vh] overflow-auto rounded-md border p-2 font-mono text-xs leading-5"
    >
      {lines.map((line, index) => {
        const spans = marks.get(index) ?? []
        const pieces: React.ReactNode[] = []
        let at = 0
        for (const [start, end, names] of spans) {
          if (start < at) continue // 겹친 자리는 앞 것이 칠한다
          if (start > at) pieces.push(line.slice(at, start))
          const focused = focus !== null && names.includes(focus)
          pieces.push(
            <mark
              key={start}
              title={names.map((name) => labels.get(name) ?? name).join(' · ')}
              data-names={names.join(' ')}
              className={`rounded-sm text-inherit ${
                focused
                  ? 'bg-primary/40 ring-primary ring-1'
                  : names.length > 1
                    ? 'bg-sky-200/70 dark:bg-sky-500/30'
                    : 'bg-amber-200/70 dark:bg-amber-500/30'
              }`}
            >
              {line.slice(start, end)}
            </mark>
          )
          at = end
        }
        if (at < line.length) pieces.push(line.slice(at))
        // `<pre>` 안에는 글자 요소만 — 줄은 `block` 인 span 으로 세운다.
        return (
          <span key={index} className="block whitespace-pre">
            <span className="text-muted-foreground mr-3 inline-block text-right select-none">
              {String(index + 1).padStart(width, ' ')}
            </span>
            {pieces}
          </span>
        )
      })}
    </pre>
  )
}
