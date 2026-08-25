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
import { AlertTriangle, BookOpen, Check, Pencil, Plus, Trash2 } from 'lucide-react'

import { DeclaredCardDialog } from '@/modules/fitting/DeclaredCardDialog'
import { ExportMenu } from '@/modules/fitting/ExportMenu'
import { STATUS_LABELS, fittingApi } from '@/modules/fitting/api'
import type {
  Fit,
  FitPreview,
  InheritedValue,
  PropertyCard,
} from '@/modules/fitting/api'
import { statisticsApi } from '@/modules/statistics/api'
import { CurveChart } from '@/modules/tests/CurveChart'
import { ApiError } from '@/shared/api/client'
import { CreatedOn } from '@/shared/components/CreatedOn'
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
import { CardBlocks } from '@/modules/fitting/CardBlocks'
import { useResource } from '@/shared/hooks/useResource'
import { formatScalar, toDisplay } from '@/shared/units'

/** 이 이상 어긋나면 눈에 띄게 한다. 커널이 같은 값에서 경고를 단다. */
const NOTABLE_RMSE = 0.05

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
  // **재료 상세는 그 재료의 카드만 본다.** 쪽으로 오지만 한 재료의 카드가
  // 상한을 넘는 일은 없다 — 넘으면 그것 자체가 알아야 할 일이다.
  const cards = useResource(() => fittingApi.cards({ material_id: materialId }), [materialId])
  const cardRows = cards.data?.items ?? []
  const [group, setGroup] = useState<GroupKey | null>(null)
  const [preview, setPreview] = useState<FitPreview | null>(null)
  const [chosen, setChosen] = useState<string | null>(null)
  // **눈으로 보고 정하는 값들이다.** 저장 모달에 있었더니 숫자를 타이핑하고
  // 저장 버튼을 누른 뒤에야 결과를 봤다 — 194 MPa 가 갈리는 결정을 눈 감고
  // 내리는 셈이었다. 여기로 올려 그래프와 함께 움직이게 한다.
  const [extrapolate, setExtrapolate] = useState('')
  const [blendWith, setBlendWith] = useState('')
  const [blendWeight, setBlendWeight] = useState(0.5)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [saving, setSaving] = useState(false)
  const [declaring, setDeclaring] = useState(false)

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

  async function run(target: GroupKey, keep = false) {
    setBusy(true)
    setError(null)
    if (!keep) {
      setPreview(null)
      setChosen(null)
    }
    try {
      const result = await fittingApi.preview({
        material_id: materialId,
        test_type_key: target.test_type_key,
        orientation: target.orientation,
        // 비우면 등록된 식 전부를 견준다.
        families: [],
        extrapolate_to: extrapolate === '' ? null : Number(extrapolate),
        // 셋을 함께 줘야 혼합 곡선이 후보에 하나 더 붙는다.
        blend_primary: blendWith && chosen ? chosen : null,
        blend_with: blendWith || null,
        blend_weight: blendWith ? blendWeight : null,
      })
      setPreview(result)
      if (!keep) {
        // 가장 잘 맞는 것을 **미리 켜 두기만** 한다. 고른 것은 아니다 — 바꿀 수
        // 있고, 바꾸는 것이 이 화면의 목적이다.
        setChosen(result.fits[0]?.family ?? null)
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('적합에 실패했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  // **조정하면 다시 그린다.** 계산은 서버가 한다 — 화면이 식을 복제하면 두
  // 곳이 갈리고, 그때 그래프가 카드와 다른 곡선을 보여 준다.
  useEffect(() => {
    if (!group || !preview) return
    const timer = setTimeout(() => void run(group, true), 350)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extrapolate, blendWith, blendWeight, chosen])

  // 묶음도 없고 카드도 없다 — 무엇을 하라고 할지가 갈리는 자리다.
  const nothing = !stats.loading && groups.length === 0 && cardRows.length === 0

  return (
    <section>
      <ErrorNotice error={stats.error ?? cards.error ?? error} className="mb-4" />

      {/* **카드가 있으면 이 말은 거짓이다.** 점탄성 카드는 통계 묶음 없이
          만들어진다(Prony 는 시험 1건에 매달린다) — 전에는 묶음이 없으면 카드도
          있을 수 없어서 같은 조건이었는데, 이제 갈린다.

          이때는 아래 목록을 아예 안 그린다. 빈 상자 둘이 겹쳐 뜨면 무엇을
          하라는 말인지가 흐려진다. */}
      {nothing && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          적합할 곡선이 없습니다. 시험 상세의 <b>처리</b> 탭에서 돌려 보고 저장한 뒤{' '}
          <b>채택</b>하면, 그 곡선이 여기의 입력이 됩니다.
          <br />
          점탄성 카드는 시험 상세의 <b>점탄성</b> 탭에서 Prony 를 맞춘 뒤 만듭니다.
        </div>
      )}

      {/* **시험이 없어도 길이 있다.** 묶음 줄 안에 두면 시험이 하나도 없는
          재료에서는 그 줄 자체가 안 떠서, 정작 이 버튼이 가장 필요한 자리에서
          사라진다(ADR 0016). */}
      <div className="mb-4 flex items-center gap-2">
        <Button size="sm" variant="outline" onClick={() => setDeclaring(true)}>
          <BookOpen className="size-4" />
          적어 둔 값으로 카드 만들기
        </Button>
        <span className="text-muted-foreground text-xs">
          시험에서 나온 값이 하나도 안 들어갑니다 — 재료의 <b>물성</b> 탭에 적은 값만
          싣습니다.
        </span>
      </div>

      <DeclaredCardDialog
        materialId={materialId}
        open={declaring}
        onClose={() => setDeclaring(false)}
        onSaved={() => void cards.reload()}
      />

      {groups.length > 0 && (
        <div className="mb-1 flex flex-wrap items-center gap-2">
          {/* **「묶음」만으로는 무엇을 고르는지 알 수 없다.** 재료의 어느
              시험·어느 방향을 볼지 고르는 자리이고, 그 안의 채택된 곡선들이
              평균 나서 대표 곡선이 된다. */}
          <span className="text-sm font-medium" title="시험 종류 · 방향으로 묶습니다. n 은 평균 낸 시편 수입니다.">
            대표 곡선 고르기
          </span>
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
            {/* '적합해 보기' 는 "적합해 보인다"(suitable) 로 읽힌다. '견주기'
                는 무엇과 무엇을 견주는지가 안 보였다 — 이 버튼이 하는 일은
                **여러 경화식을 같은 곡선에 맞춰 나란히 놓고, 시험 구간 밖을
                얼마나 늘릴지 정하게 하는 것**이다. 저장은 아직 아니다. */}
            {busy ? '맞춰 보는 중…' : '경화식 맞춰 보기'}
          </Button>
        </div>
      )}

      {groups.length > 0 && (
        // **한 줄로 무엇을 하는 자리인지 말한다.** 단추 이름만으로는 담기지
        // 않는다 — 맞추는 것과 늘리는 것이 한 화면에서 일어난다.
        <p className="text-muted-foreground mb-4 text-xs">
          여러 <b>경화식</b>(Voce · Swift · Hockett-Sherby …)을 같은 곡선에 맞춰{' '}
          <b>나란히 놓습니다.</b> 측정 구간에서는 거의 겹치는 식들이 그 밖에서 크게
          갈리므로, <b>해석에 필요한 변형률까지 얼마나 늘릴지</b>를 그림을 보고 정합니다.
          누른다고 저장되지 않습니다.
        </p>
      )}

      {preview && (
        <FitComparison
          extrapolate={extrapolate}
          onExtrapolate={setExtrapolate}
          blendWith={blendWith}
          onBlendWith={setBlendWith}
          blendWeight={blendWeight}
          onBlendWeight={setBlendWeight}
          preview={preview}
          chosen={chosen}
          onChoose={setChosen}
          onSave={() => setSaving(true)}
        />
      )}

      {!nothing && (
        <CardList
          cards={cardRows}
          loading={cards.loading}
          onChanged={() => cards.reload()}
          onError={setError}
        />
      )}

      {group && (
        <SaveDialog
          candidates={preview?.fits ?? []}
          extrapolate={extrapolate}
          blendWith={blendWith}
          blendWeight={blendWeight}
          open={saving}
          materialId={materialId}
          group={group}
          family={chosen}
          elastic={preview?.elastic ?? []}
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
  extrapolate,
  onExtrapolate,
  blendWith,
  onBlendWith,
  blendWeight,
  onBlendWeight,
}: {
  preview: FitPreview
  chosen: string | null
  onChoose: (family: string | null) => void
  onSave: () => void
  /** 여기까지 늘려 **그린다.** 저장은 아직 아니다. */
  extrapolate: string
  onExtrapolate: (value: string) => void
  blendWith: string
  onBlendWith: (value: string) => void
  blendWeight: number
  onBlendWeight: (value: number) => void
}) {
  // **`chosen === null` 은 '아직 안 골랐다' 가 아니라 '식을 안 쓴다' 다.**
  // 전에는 여기서 `?? preview.fits[0]` 로 되돌려서, 표만 쓰겠다는 선택이
  // 화면에서 사라졌다 — 서버는 받는데 갈 길이 없었다.
  const fit = chosen === null ? null : preview.fits.find((item) => item.family === chosen)
  // **축 이름을 화면이 정하지 않는다.** 금속은 진응력·진소성변형률에, 고무는
  // 공칭에 맞춘다 — 그래프 축이 "진소성변형률" 이라고 붙으면 그것은 거짓말이고,
  // 그 거짓말은 화면에서만 보인다. 식 없이 표만 쓸 때는 소성 표라서 금속 축이다.
  const xLabel = `${fit?.x_label ?? '진소성변형률'} (%)`
  const yLabel = `${fit?.y_label ?? '진응력'} (MPa)`
  // 늘리기 칸에 붙일 축 이름. 그래프 축과 달리 단위 접미사가 없다.
  const axisLabel = fit?.x_label ?? '진소성변형률'
  // **늘릴 수 있는 식인가.** 늘리는 것은 소성 표를 만드는 일이라 `hardening`
  // 에서만 뜻이 있다. 서버도 같은 이유로 저장을 거절하므로(MNX-FITTING-0014)
  // 여기서 안 잠그면 **보여 준 것을 저장 못 하는** 상태가 된다.
  //
  // 식을 안 고른 상태(표만 쓰기)에서도 잠근다 — 늘릴 근거가 되는 식이 없다.
  const stretchable = fit !== null && fit !== undefined && fit.block === 'hardening'
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
        {/* **눈으로 보고 정하는 값들이다.** 저장 모달에 있었을 때는 숫자를
            타이핑하고 저장한 뒤에야 결과를 봤다 — 194 MPa 가 갈리는 결정을
            눈 감고 내리는 셈이었다. */}
        <div className="bg-muted/40 grid gap-3 rounded-md p-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            {/* **축 이름을 하드코딩하지 않는다.** 고무는 공칭 변형률이고, 여기에
                "진소성변형률" 이라고 붙으면 그것은 거짓말이다. 식이 자기 축을
                선언하므로(ADR 0013) 그것을 그대로 쓴다. */}
            <Label htmlFor="extrapolate" title="시험이 준 구간 밖까지 식으로 그려 봅니다. 저장하면 그 구간이 소성 표에 들어갑니다.">
              시험 구간 밖까지 늘리기 ({axisLabel})
            </Label>
            <Input
              id="extrapolate"
              inputMode="decimal"
              placeholder={stretchable ? '비우면 측정 구간까지만' : '이 식은 늘리지 않습니다'}
              value={stretchable ? extrapolate : ''}
              onChange={(event) => onExtrapolate(event.target.value)}
              disabled={!stretchable}
            />
            <p className="text-muted-foreground text-xs">
              {stretchable ? (
                <>
                  인장시험은 <b>네킹까지</b>만 줍니다(강판이면 0.1~0.25). 충돌 해석은
                  0.5~1.5 를 씁니다 — 그래프의{' '}
                  <b>세로선 오른쪽이 식이 지어낸 구간</b>입니다.
                </>
              ) : fit ? (
                <>
                  <b>{fit.label}</b> 은 소성 표를 만드는 식이 아닙니다. 덱의
                  초탄성 블록은 표가 아니라 <b>계수</b>를 받으므로 늘릴 자리가
                  없습니다.
                </>
              ) : (
                <>
                  <b>식을 골라야 늘릴 수 있습니다.</b> 표만 저장하면 측정한 점이
                  그대로 덱에 실리고, 그 밖을 채울 근거가 없습니다.
                </>
              )}
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="blend">섞을 식</Label>
            <select
              id="blend"
              className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
              value={blendWith}
              onChange={(event) => onBlendWith(event.target.value)}
              disabled={chosen === null}
            >
              <option value="">안 섞음</option>
              {preview.fits
                .filter((item) => item.family !== chosen && !item.family.includes('+'))
                .map((item) => (
                  <option key={item.family} value={item.family}>
                    {item.label}
                  </option>
                ))}
            </select>
            {blendWith !== '' && (
              <>
                <input
                  aria-label="섞는 비중"
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={blendWeight}
                  onChange={(event) => onBlendWeight(Number(event.target.value))}
                  className="w-full"
                />
                <p className="text-muted-foreground text-xs">
                  고른 식 <b>{blendWeight.toFixed(2)}</b> : 섞을 식{' '}
                  <b>{(1 - blendWeight).toFixed(2)}</b>. <b>데이터가 이 값을 정해 주지
                  않습니다</b> — 적합 구간에서는 어느 값이든 비슷하게 맞으므로, 얼마나
                  보수적으로 볼지가 정합니다.
                </p>
              </>
            )}
          </div>
        </div>

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
              xLabel={xLabel}
              yLabel={yLabel}
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
              xLabel={xLabel}
              yLabel={yLabel}
              height={300}
              // 늘려 그린 때만 긋는다. 안 늘렸으면 경계가 곧 곡선 끝이라 선이 겹친다.
              marker={
                fit.extrapolated_to === null || fit.extrapolated_to === undefined
                  ? undefined
                  : { x: fit.strain_max, label: '여기까지 시험' }
              }
            />

            {fit.extrapolated_to != null && (
              <p className="text-muted-foreground text-xs">
                세로선 오른쪽 <b>{fit.strain_max.toPrecision(2)} ~{' '}
                {fit.extrapolated_to.toPrecision(2)}</b> 구간은 측정한 것이 아니라{' '}
                <b>{fit.label} 이 지어낸 값</b>입니다. 식마다 여기서 갈리므로, 후보를
                바꿔 가며 끝값을 견주고 정하세요.
              </p>
            )}

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
  // **화면이 물성의 이름을 모른다.** 무엇을 그릴지는 이 선언이 정한다.
  const blocks = useResource(() => fittingApi.blocks(), [])
  const specs = blocks.data ?? []
  const [renaming, setRenaming] = useState<string | null>(null)

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
          <RenameCardDialog
            card={card}
            open={renaming === card.id}
            onClose={() => setRenaming(null)}
            onSaved={() => {
              setRenaming(null)
              onChanged()
            }}
          />
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{card.label}</span>
            {/* **이 카드가 언제 것인가.** 같은 재료에 카드가 쌓이면 그 물음이
                먼저 온다 — 어느 것이 최신인지 이름만으로는 안 보인다. */}
            <CreatedOn at={card.created_at} label="만듦" />
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
            {/* **시험에서 나온 카드와 같은 모양으로 그리면 안 된다.**
                시험종류가 비어 있으면 `· · 시편 0개` 로 보이는데, 그것은
                "시험이 지워졌다" 로 읽힌다. 무엇인지 말로 적는다. */}
            <span className="text-muted-foreground text-sm">
              {card.test_type_key === null ? (
                <span className="text-amber-700 dark:text-amber-500">
                  시험 없음 · 적어 둔 값
                </span>
              ) : (
                <>
                  {card.test_type_key} · {card.orientation} · 시편{' '}
                  {String(card.source.sample_count ?? '?')}개 · {card.point_count}점
                </>
              )}
            </span>

            <div className="ml-auto flex gap-1">
              <ExportMenu card={card} formats={formats.data ?? []} onError={onError} />
              {card.status === 'draft' && (
                <>
                  {/* **오타를 고치려고 적합을 다시 돌리게 하지 않는다.** */}
                  <Button
                    size="sm"
                    variant="ghost"
                    title="이름·메모 고치기 (값은 안 바뀝니다)"
                    onClick={() => setRenaming(card.id)}
                  >
                    <Pencil className="size-3.5" />
                  </Button>
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

          {/* **화면이 물성의 이름을 모른다.** 선언이 무엇을 그릴지 정한다 —
              새 물성이 붙어도 이 파일은 안 고친다. */}
          <CardBlocks specs={specs} card={card} />
        </div>
      ))}
    </div>
  )
}

function SaveDialog({
  candidates,
  extrapolate,
  blendWith,
  blendWeight,
  open,
  materialId,
  group,
  family,
  elastic,
  onClose,
  onSaved,
}: {
  /**
   * 비교 화면에서 정한 것. **여기서 다시 고르지 않는다** — 늘린 한계와 섞는
   * 비중은 곡선을 보면서 정하는 값이라, 그래프가 없는 모달에서 숫자만 바꾸면
   * 194 MPa 가 갈리는 결정을 눈 감고 내리게 된다.
   */
  extrapolate: string
  blendWith: string
  blendWeight: number
  /** 섞을 상대의 이름을 적기 위해서만 쓴다. */
  candidates: Fit[]
  open: boolean
  materialId: string
  group: GroupKey
  family: string | null
  /** 비워 두면 카드에 들어갈 값들. **적합 응답이 준 그대로다.** */
  elastic: InheritedValue[]
  onClose: () => void
  onSaved: () => void
}) {
  const [label, setLabel] = useState('')
  const [poisson, setPoisson] = useState('')
  const [density, setDensity] = useState('')
  // **빈칸으로 두면 사람이 또 적는다.** 재료·시료에 이미 있는 값을 모달이
  // 모르면 같은 값을 두 번 적게 되고, 두 곳이 갈리면 어느 쪽이 맞는지 알 수
  // 없다. 여기서는 보여 주기만 한다 — 빈칸으로 보내면 서버가 물려받는다.
  //
  // 값은 **적합 응답이 준다.** 재료 API 를 따로 부르면 상속 규칙이 두 벌이 되고,
  // 어긋나는 순간 모달이 거짓말을 한다.
  const inherited = (key: string) => elastic.find((row) => row.key === key)
  const inheritedPlaceholder = (key: string) => {
    const row = inherited(key)
    return row?.value == null
      ? '비워 두면 넣지 않음'
      : `${Number(row.value.toPrecision(6))} (물려받음)`
  }
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
        blend_with: blendWith === '' ? null : blendWith,
        blend_weight: blendWith === '' ? null : blendWeight,
        extrapolate_to: extrapolate === '' ? null : Number(extrapolate),
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
      <DialogContent className="sm:max-w-2xl">
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
            {/* **빈칸이 곧 '물려받는다' 는 뜻이다.**
                재료·시료에 이미 있는 값을 여기서 또 적게 하면 두 곳이 갈리고,
                그때 어느 쪽이 맞는지 판정할 근거가 없다. 그래서 모달은 값을
                복사해 채우지 않고, **어디서 무엇이 올지**를 보여 준다. */}
            <div className="space-y-1.5">
              <Label htmlFor="poisson">푸아송비</Label>
              <Input
                id="poisson"
                inputMode="decimal"
                placeholder={inheritedPlaceholder('poisson_ratio')}
                value={poisson}
                onChange={(event) => setPoisson(event.target.value)}
              />
              <InheritNote row={inherited('poisson_ratio')} overridden={poisson !== ''} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="density">밀도 (kg/m³)</Label>
              <Input
                id="density"
                inputMode="decimal"
                placeholder={inheritedPlaceholder('density')}
                value={density}
                onChange={(event) => setDensity(event.target.value)}
              />
              <InheritNote row={inherited('density')} overridden={density !== ''} />
            </div>
          </div>

          <p className="text-muted-foreground text-xs">
            값은 <b>재료·시료에서 물려받습니다</b> — 비워 두면 그 값이 들어갑니다.
            여기 적으면 그 값이 이기고, 카드에 '직접 입력' 으로 남습니다. 어느 쪽이든
            카드는 <b>값과 출처를 함께</b> 박아 둡니다.
          </p>

          {/* **여기서는 확인만 한다.** 늘린 한계도 섞는 비중도 그래프를 보며
              정하는 값이라, 곡선이 없는 이 자리에서 숫자만 바꾸면 무엇이 달라지는지
              모르는 채 정하게 된다. 고치려면 비교 화면으로 돌아간다. */}
          <div className="bg-muted/40 space-y-1 rounded-md p-3 text-xs">
            <p className="text-sm font-medium">비교 화면에서 정한 것</p>
            <p>
              <span className="text-muted-foreground">늘릴 한계</span>{' '}
              {extrapolate === '' ? (
                <b>측정 구간까지만</b>
              ) : (
                <b>진소성변형률 {extrapolate} 까지</b>
              )}
            </p>
            <p>
              <span className="text-muted-foreground">섞을 식</span>{' '}
              {blendWith === '' ? (
                <b>안 섞음</b>
              ) : (
                <b>
                  {candidates.find((item) => item.family === blendWith)?.label ?? blendWith}{' '}
                  비중 {blendWeight.toFixed(2)}
                </b>
              )}
            </p>
            <p className="text-muted-foreground pt-1">
              바꾸려면 이 창을 닫고 <b>비교 화면</b>에서 조정하세요 — 곡선이 함께
              움직이는 것을 보고 정하는 값입니다.
            </p>
          </div>

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

/**
 * 이 칸이 비었을 때 무엇이 들어가는가.
 *
 * **없다는 사실만 알려 주고 길을 안 주면 결국 다시 헤맨다.** 그래서 어디에
 * 채우면 되는지까지 적는다.
 */
function InheritNote({ row, overridden }: { row?: InheritedValue; overridden: boolean }) {
  if (overridden) {
    return <p className="text-muted-foreground text-xs">직접 입력한 값을 씁니다.</p>
  }
  if (!row) return null
  if (row.value !== null) {
    return (
      <p className="text-muted-foreground text-xs">
        {row.source === 'sample' ? '시료에서 잰 값' : '재료의 공칭값'}을 씁니다.
      </p>
    )
  }
  // 못 물려받는 이유는 서버가 안다 — 화면이 다시 판정하지 않는다.
  return (
    <p className="text-xs text-amber-700 dark:text-amber-500">
      {row.detail ?? '물려받을 값이 없습니다.'}
    </p>
  )
}

/**
 * 초안 카드의 이름·메모 고치기.
 *
 * **불변이 오타까지 지키고 있었다.** 값(`elastic`·`hardening`·`table`)은 못
 * 바꾸는 것이 맞다 — 그래야 "이 카드가 무엇으로 나왔나" 에 항상 답할 수 있다.
 * 그런데 이름을 고칠 길도 없어서, 오타 하나에 카드를 지우고 적합을 다시 돌려야
 * 했다. 그건 불변이 지키려던 것과 아무 상관이 없다.
 *
 * 확정된 카드는 이름도 못 바꾼다. 그 이름으로 덱이 이미 나갔을 수 있다.
 */
function RenameCardDialog({
  card,
  open,
  onClose,
  onSaved,
}: {
  card: PropertyCard
  open: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const [label, setLabel] = useState(card.label)
  const [note, setNote] = useState(card.note ?? '')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setLabel(card.label)
      setNote(card.note ?? '')
      setFailure(null)
    }
  }, [open, card])

  async function submit() {
    setBusy(true)
    setFailure(null)
    try {
      await fittingApi.update(card.id, { label, note: note === '' ? null : note })
      onSaved()
    } catch (error) {
      setFailure(error instanceof ApiError ? error.message : '저장하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>카드 이름 고치기</DialogTitle>
          <DialogDescription>
            이름과 메모만 바뀝니다. <b>값은 못 바꿉니다</b> — 다시 적합하려면 새 카드를
            만드세요.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="rename-label">이름</Label>
            <Input
              id="rename-label"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rename-note">메모</Label>
            <Input
              id="rename-note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>
          {failure && <p className="text-destructive text-sm">{failure}</p>}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={submit} disabled={busy || label.trim() === ''}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
