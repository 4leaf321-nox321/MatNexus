/**
 * CAE 카드 — **해석에 들어가는 값을 만드는 화면.**
 *
 * 여기서 나온 숫자가 솔버에 들어가고, 그 해석으로 설계가 정해진다. 그래서 이
 * 화면이 지키는 것은 하나다 — **믿을 근거를 함께 보여 준다.**
 *
 * ## 어느 식이 맞는지 화면이 고르지 않는다
 *
 * 여러 식을 같은 데이터에 맞춰 나란히 놓고 상대 RMSE 로 정렬만 한다. 적합 구간에서
 * 거의 같은 두 식이 그 밖에서는 갈린다 — Swift 는 계속 올라가고 Voce 는 포화한다.
 * 어디까지 쓸 것인지가 선택을 바꾸고, 그것은 해석하는 사람이 안다.
 *
 * ## 겹쳐 그린다
 *
 * RMSE 가 작아도 항복 근처만 크게 어긋나 있을 수 있다. 그것은 숫자로 안 보이고
 * 모양으로 보인다.
 */

import { useEffect, useState } from 'react'
import { AlertTriangle, Check, FileDown, Plus, Trash2 } from 'lucide-react'

import { STATUS_LABELS, fittingApi } from '@/modules/fitting/api'
import type { ExportFormat, Fit, FitPreview, PropertyCard } from '@/modules/fitting/api'
import { statisticsApi } from '@/modules/statistics/api'
import { CurveChart } from '@/modules/tests/CurveChart'
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/shared/components/ui/dropdown-menu'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { useResource } from '@/shared/hooks/useResource'
import { formatScalar, toDisplay } from '@/shared/units'

/** 이 이상 어긋나면 눈에 띄게 한다. 커널이 같은 값에서 경고를 단다. */
const NOTABLE_RMSE = 0.05

/**
 * 형식이 요구하는 값이 카드에 있는가. **서버가 한국어 이름으로 요구를 준다**
 * (`ExportFormatOut.requires`) — 화면이 그 이름을 카드 필드에 이어 붙인다.
 */
const HAS: Record<string, (card: PropertyCard) => boolean> = {
  탄성계수: (card) => typeof card.elastic.youngs_modulus === 'number',
  푸아송비: (card) => typeof card.elastic.poisson_ratio === 'number',
  밀도: (card) => typeof card.elastic.density === 'number',
}

interface Props {
  materialId: string
}

interface GroupKey {
  test_type_key: string
  test_type_label: string
  orientation: string
  sample_count: number
}

export function FittingPanel({ materialId }: Props) {
  const stats = useResource(() => statisticsApi.forMaterial(materialId), [materialId])
  const cards = useResource(() => fittingApi.cards(materialId), [materialId])
  const [group, setGroup] = useState<GroupKey | null>(null)
  const [preview, setPreview] = useState<FitPreview | null>(null)
  const [chosen, setChosen] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [saving, setSaving] = useState(false)

  const groups: GroupKey[] = (stats.data?.groups ?? [])
    // **채택된 것이 있으면 적합할 수 있다.** 1건이면 그 곡선이 곧 입력이다 —
    // 평균 낼 상대가 없다는 것과 그릴 곡선이 없다는 것은 다르다.
    //
    // 여기 2건 문턱이 남아 있어서, 물성 탭에는 곡선이 뜨는데 이 탭에서는
    // "적합할 대표 곡선이 없습니다" 가 떴다. 서버는 이미 1건을 받는다.
    // 여러 개가 낫다는 것은 막을 이유가 아니라 **적을 이유**다 — 1건으로 만든
    // 카드에는 그 사실이 근거와 솔버 덱 머리글에 남는다.
    .filter((item) => item.sample_count >= 1)
    .map((item) => ({
      test_type_key: item.test_type_key,
      test_type_label: item.test_type_label,
      orientation: item.orientation,
      sample_count: item.sample_count,
    }))

  // 재료가 바뀌면 고른 묶음을 버린다. 라우트 파라미터만 바뀌면 이 컴포넌트는
  // 다시 마운트되지 않아, 남겨 두면 **다른 재료의 묶음을 적합하려 든다.**
  useEffect(() => {
    setGroup(null)
    setPreview(null)
    setChosen(null)
  }, [materialId])

  useEffect(() => {
    if (!group && groups.length > 0) setGroup(groups[0])
  }, [group, groups])

  async function run(target: GroupKey) {
    setBusy(true)
    setError(null)
    setPreview(null)
    setChosen(null)
    try {
      const result = await fittingApi.preview({
        material_id: materialId,
        test_type_key: target.test_type_key,
        orientation: target.orientation,
      })
      setPreview(result)
      // 가장 잘 맞는 것을 **미리 켜 두기만** 한다. 고른 것은 아니다 — 바꿀 수 있고,
      // 바꾸는 것이 이 화면의 목적이다.
      setChosen(result.fits[0]?.family ?? null)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('적합에 실패했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <ErrorNotice error={stats.error ?? cards.error ?? error} className="mb-4" />

      {!stats.loading && groups.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          적합할 곡선이 없습니다. 시험 상세의 <b>처리</b> 탭에서 돌려 보고 저장한 뒤{' '}
          <b>채택</b>하면, 그 곡선이 여기의 입력이 됩니다.
        </div>
      )}

      {groups.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">묶음</span>
          {groups.map((item) => {
            const key = `${item.test_type_key}-${item.orientation}`
            const active =
              group?.test_type_key === item.test_type_key &&
              group?.orientation === item.orientation
            return (
              <Button
                key={key}
                size="sm"
                variant={active ? 'default' : 'outline'}
                onClick={() => {
                  setGroup(item)
                  setPreview(null)
                  setChosen(null)
                }}
              >
                {item.test_type_label} · {item.orientation}
                <span className="opacity-70">n={item.sample_count}</span>
              </Button>
            )
          })}
          <Button
            size="sm"
            variant="secondary"
            className="ml-auto"
            disabled={!group || busy}
            onClick={() => group && run(group)}
          >
            {/* '적합해 보기' 는 "적합해 보인다"(suitable) 로 읽힌다. 이 버튼이
                하는 일은 여러 식을 같은 곡선에 맞춰 **나란히 놓는 것**이다. */}
            {busy ? '맞춰 보는 중…' : '경화식 견주기'}
          </Button>
        </div>
      )}

      {preview && (
        <FitComparison
          preview={preview}
          chosen={chosen}
          onChoose={setChosen}
          onSave={() => setSaving(true)}
        />
      )}

      <CardList
        cards={cards.data ?? []}
        loading={cards.loading}
        onChanged={() => cards.reload()}
        onError={setError}
      />

      {group && (
        <SaveDialog
          open={saving}
          materialId={materialId}
          group={group}
          family={chosen}
          onClose={() => setSaving(false)}
          onSaved={() => {
            setSaving(false)
            cards.reload()
          }}
        />
      )}
    </section>
  )
}

function FitComparison({
  preview,
  chosen,
  onChoose,
  onSave,
}: {
  preview: FitPreview
  chosen: string | null
  onChoose: (family: string | null) => void
  onSave: () => void
}) {
  // **`chosen === null` 은 '아직 안 골랐다' 가 아니라 '식을 안 쓴다' 다.**
  // 전에는 여기서 `?? preview.fits[0]` 로 되돌려서, 표만 쓰겠다는 선택이
  // 화면에서 사라졌다 — 서버는 받는데 갈 길이 없었다.
  const fit = chosen === null ? null : preview.fits.find((item) => item.family === chosen)
  // 표시 단위로 맞춘다. 축만 바꾸고 점을 안 바꾸면 1000배 어긋난다.
  const shown = (points: [number, number][]): [number, number][] =>
    points.map(([x, y]) => [toDisplay(x, '1', 'strain'), toDisplay(y, 'Pa')])

  return (
    <div className="mb-6 rounded-md border">
      <header className="flex flex-wrap items-center gap-2 border-b p-3">
        <h3 className="font-medium">경화식 후보</h3>
        <span className="text-muted-foreground text-sm">
          {/* 1개짜리를 '대표 곡선' 이라 쓰면 여러 시편의 평균으로 읽힌다. */}
          {preview.sample_count === 1
            ? `시편 1개의 곡선 ${preview.source_points.length}점`
            : `시편 ${preview.sample_count}개의 대표 곡선 ${preview.source_points.length}점`}
        </span>
        <Button size="sm" className="ml-auto" onClick={onSave}>
          <Plus className="size-3.5" />
          이 값으로 카드 만들기
        </Button>
      </header>

      <div className="space-y-4 p-3">
        {preview.notes.length > 0 && (
          <ul className="text-muted-foreground space-y-1 text-xs">
            {preview.notes.map((note) => (
              <li key={note} className="border-l-2 pl-2">
                {note}
              </li>
            ))}
          </ul>
        )}

        {/* **순서만 준다. 고르지는 않는다.** 적합 구간에서 비슷한 두 식이 그
            밖에서 갈린다 — 어디까지 쓸 것인지는 해석하는 사람이 안다. */}
        <div className="grid gap-2 sm:grid-cols-3">
          {preview.fits.map((item) => (
            <FitCard
              key={item.family}
              fit={item}
              active={item.family === fit?.family}
              onClick={() => onChoose(item.family)}
            />
          ))}
          {/* **식을 안 쓰는 것도 선택이다.**
              솔버 덱의 소성 블록에 들어가는 것은 어느 쪽을 고르든 **표**다
              (`*PLASTIC` · `/FUNCT`). 식은 카드에 파라미터와 적합도로 남고
              덱에는 참고 주석으로 들어간다. 식이 안 맞는 재료 — 항복 근처가
              꺾이거나 이중 항복이 있는 것 — 에서는 억지로 맞춘 식보다 표가
              정확하다. */}
          <button
            type="button"
            onClick={() => onChoose(null)}
            className={`rounded-md border p-2 text-left ${
              chosen === null ? 'border-primary ring-primary/30 ring-2' : ''
            }`}
          >
            <p className="text-sm font-medium">식 없이 표만</p>
            <p className="text-muted-foreground mt-1 text-xs">
              측정한 곡선을 그대로 씁니다. 식이 안 맞는 재료에서는 이쪽이 정확합니다.
            </p>
          </button>
        </div>

        {chosen === null && (
          <>
            <CurveChart
              points={shown(preview.source_points as [number, number][])}
              pointsLabel={preview.sample_count === 1 ? '시편 1개의 곡선' : '대표 곡선'}
              xLabel="진소성변형률 (%)"
              yLabel="진응력 (MPa)"
              height={300}
            />
            <p className="text-muted-foreground text-xs">
              이 {preview.source_points.length}점이 그대로 카드의 표가 되고, 솔버
              덱에도 이 값이 들어갑니다. 식을 고르면 파라미터와 적합도가 카드에
              함께 남지만, <b>덱의 소성 블록은 어느 쪽이든 이 표입니다.</b>
            </p>
          </>
        )}

        {fit && (
          <>
            <CurveChart
              points={shown(preview.source_points as [number, number][])}
              overlay={{
                points: shown(fit.curve as [number, number][]),
                label: `${fit.label} 적합`,
              }}
              pointsLabel={preview.sample_count === 1 ? '시편 1개의 곡선' : '대표 곡선'}
              xLabel="진소성변형률 (%)"
              yLabel="진응력 (MPa)"
              height={300}
            />

            <div>
              <h4 className="mb-1.5 text-sm font-medium">{fit.label} 파라미터</h4>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {fit.parameters.map((item) => (
                  <div key={item.name} className="rounded-md border p-2">
                    <p className="font-mono text-xs">{item.name}</p>
                    <p className="tabular-nums">{formatScalar(item.value, item.si_unit)}</p>
                    {/* **경계에 붙으면 그 값은 데이터가 정한 것이 아니다.** */}
                    <p className="text-muted-foreground mt-0.5 font-mono text-[11px]">
                      [{item.lower.toPrecision(3)}, {item.upper.toPrecision(3)}]
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <ul className="text-muted-foreground space-y-1 text-xs">
              {fit.notes.map((note) => (
                <li key={note} className="border-l-2 pl-2">
                  {note}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  )
}

function FitCard({
  fit,
  active,
  onClick,
}: {
  fit: Fit
  active: boolean
  onClick: () => void
}) {
  const poor = fit.relative_rmse >= NOTABLE_RMSE
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md border p-3 text-left transition ${
        active ? 'border-primary bg-primary/5' : 'hover:bg-muted/40'
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="font-medium">{fit.label}</span>
        {active && <Check className="text-primary size-3.5" />}
        {poor && <AlertTriangle className="size-3.5 text-amber-600 dark:text-amber-500" />}
      </div>
      <dl className="text-muted-foreground mt-1 space-y-0.5 text-xs">
        <div className="flex justify-between">
          <dt>상대 RMSE</dt>
          <dd className={`tabular-nums ${poor ? 'font-medium text-amber-700' : ''}`}>
            {(fit.relative_rmse * 100).toPrecision(3)}%
          </dd>
        </div>
        <div className="flex justify-between">
          <dt>R²</dt>
          <dd className="tabular-nums">{fit.r_squared.toFixed(5)}</dd>
        </div>
        <div className="flex justify-between">
          <dt>최대 잔차</dt>
          <dd className="tabular-nums">{formatScalar(fit.max_residual, 'Pa')}</dd>
        </div>
      </dl>
    </button>
  )
}

function CardList({
  cards,
  loading,
  onChanged,
  onError,
}: {
  cards: PropertyCard[]
  loading: boolean
  onChanged: () => void
  onError: (error: Error) => void
}) {
  // 카드마다 부르지 않는다 — 목록에 20장이 있으면 같은 요청이 20번 나간다.
  const formats = useResource(() => fittingApi.formats(), [])

  async function act(action: () => Promise<unknown>) {
    try {
      await action()
      onChanged()
    } catch (caught) {
      onError(caught instanceof Error ? caught : new Error('처리하지 못했습니다.'))
    }
  }

  if (loading) return null
  if (cards.length === 0) {
    return (
      <div className="text-muted-foreground rounded-md border py-8 text-center text-sm">
        만든 카드가 없습니다.
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <h3 className="font-medium">물성 카드</h3>
      {cards.map((card) => (
        <div key={card.id} className="rounded-md border p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{card.label}</span>
            <Badge
              variant={
                card.status === 'published'
                  ? 'default'
                  : card.status === 'deprecated'
                    ? 'outline'
                    : 'secondary'
              }
            >
              {STATUS_LABELS[card.status] ?? card.status}
            </Badge>
            <span className="text-muted-foreground text-sm">
              {card.test_type_key} · {card.orientation} · 시편{' '}
              {String(card.source.sample_count ?? '?')}개 · {card.point_count}점
            </span>

            <div className="ml-auto flex gap-1">
              <ExportMenu card={card} formats={formats.data ?? []} onError={onError} />
              {card.status === 'draft' && (
                <>
                  <Button
                    size="sm"
                    onClick={() => act(() => fittingApi.publish(card.id))}
                    title="확정 — 부서 관리자만. 올린 뒤에는 값을 바꿀 수 없습니다."
                  >
                    확정
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => act(() => fittingApi.remove(card.id))}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </>
              )}
              {card.status === 'published' && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => act(() => fittingApi.deprecate(card.id))}
                  title="내리기 — 지우지 않습니다. 이 값으로 해석이 돌았을 수 있습니다."
                >
                  내리기
                </Button>
              )}
            </div>
          </div>

          <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
            <Item
              label="탄성계수"
              value={
                typeof card.elastic.youngs_modulus === 'number'
                  ? formatScalar(card.elastic.youngs_modulus, 'Pa')
                  : '—'
              }
            />
            <Item
              label="푸아송비"
              value={
                typeof card.elastic.poisson_ratio === 'number'
                  ? String(card.elastic.poisson_ratio)
                  : '—'
              }
            />
            <Item
              label="경화식"
              value={typeof card.hardening.label === 'string' ? card.hardening.label : '표만'}
            />
            <Item
              label="상대 RMSE"
              value={
                typeof card.hardening.relative_rmse === 'number'
                  ? `${(card.hardening.relative_rmse * 100).toPrecision(3)}%`
                  : '—'
              }
            />
          </dl>

          {/* **적합 구간을 카드에 적어 둔다.** 이 밖은 외삽이고 식마다 전혀
              다른 값이 나온다. */}
          {typeof card.hardening.strain_max === 'number' && (
            <p className="text-muted-foreground mt-2 text-xs">
              적합 구간: 진소성변형률{' '}
              {(Number(card.hardening.strain_min) * 100).toPrecision(3)}% ~{' '}
              {(Number(card.hardening.strain_max) * 100).toPrecision(3)}%. 이 밖은
              검증되지 않았습니다.
            </p>
          )}
        </div>
      ))}
    </div>
  )
}

function ExportMenu({
  card,
  formats,
  onError,
}: {
  card: PropertyCard
  formats: ExportFormat[]
  onError: (error: Error) => void
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="outline">
          <FileDown className="size-3.5" />
          내보내기
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        {formats.map((format) => {
          // **누르기 전에 알려 준다.** 내려받기를 누른 뒤에 "푸아송비가
          // 없습니다" 를 보는 것은 늦다.
          const missing = format.requires.filter(
            (name) => !HAS[name]?.(card as PropertyCard)
          )
          return (
            <DropdownMenuItem
              key={format.key}
              disabled={missing.length > 0}
              onSelect={() => {
                fittingApi
                  .download(card.id, format, card.label)
                  .catch((caught: unknown) =>
                    onError(
                      caught instanceof Error ? caught : new Error('내보내지 못했습니다.')
                    )
                  )
              }}
            >
              <div>
                <p className="text-sm">{format.label}</p>
                <p className="text-muted-foreground text-xs">
                  {missing.length > 0
                    ? `${missing.join('·')} 가 카드에 없어 내보낼 수 없습니다.`
                    : format.describe}
                </p>
              </div>
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  )
}

function SaveDialog({
  open,
  materialId,
  group,
  family,
  onClose,
  onSaved,
}: {
  open: boolean
  materialId: string
  group: GroupKey
  family: string | null
  onClose: () => void
  onSaved: () => void
}) {
  const [label, setLabel] = useState('')
  const [poisson, setPoisson] = useState('')
  const [density, setDensity] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open) setLabel(`${group.test_type_label} ${group.orientation}`)
  }, [open, group])

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await fittingApi.create({
        material_id: materialId,
        test_type_key: group.test_type_key,
        orientation: group.orientation,
        label,
        family,
        // **빈칸은 보내지 않는다.** 0.3 으로 채우면 그것이 측정값인지 기본값인지
        // 나중에 알 수 없다.
        poisson_ratio: poisson === '' ? null : Number(poisson),
        density: density === '' ? null : Number(density),
        note: note === '' ? null : note,
      })
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장에 실패했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>물성 카드 만들기</DialogTitle>
          <DialogDescription>
            초안으로 저장됩니다. 확정은 부서 관리자가 하고, 확정한 뒤에는 값을 바꿀 수
            없습니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="card-label">이름</Label>
            <Input
              id="card-label"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="poisson">푸아송비</Label>
              <Input
                id="poisson"
                inputMode="decimal"
                placeholder="비워 두면 넣지 않음"
                value={poisson}
                onChange={(event) => setPoisson(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="density">밀도 (kg/m³)</Label>
              <Input
                id="density"
                inputMode="decimal"
                placeholder="비워 두면 넣지 않음"
                value={density}
                onChange={(event) => setDensity(event.target.value)}
              />
            </div>
          </div>

          {/* **인장시험이 주지 않는 값이다.** 왜 비어 있는지 화면이 말해야, 다음
              사람이 0.3 을 습관처럼 적어 넣지 않는다. */}
          <p className="text-muted-foreground text-xs">
            푸아송비와 밀도는 인장시험이 주지 않습니다. 아는 값이 있으면 넣고, 없으면
            비워 두세요 — 기본값으로 채우면 그것이 측정값인지 나중에 알 수 없습니다.
          </p>

          <div className="space-y-1.5">
            <Label htmlFor="note">메모</Label>
            <Input
              id="note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>

          <p className="text-muted-foreground text-xs">
            경화식: <b>{family ?? '없음 — 표만 저장합니다'}</b>. 많은 솔버가 식보다
            표를 그대로 받습니다.
          </p>
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={submit} disabled={busy || label.trim() === ''}>
            초안으로 저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
