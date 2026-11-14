/**
 * 주파수 지정 온도별 탄성률 표 — **DMA 온도별 E′ 를 잰 물성으로**(2026-10-22, v1.285.0 보고).
 *
 * 전에는 재료에 「적어 둔 값」 으로 출처를 추정이라 적어 넣을 수밖에 없었다. 다온도 파일은 온도마다
 * 곡선이 따로라 처리 단계로는 표가 안 나와, 마스터커브처럼 시험의 곡선 여럿을 읽는다(서버).
 * 표에서 카드(「온도별 저장 탄성률」 블록)를 만든다 — 정적 탄성계수 칸에는 넣지 않는다.
 *
 * **다른 시편의 표와 평균해 카드를 만들 수 있다**(2026-10-22). 시편 하나의 카드는 「그 시편의
 * 값」 이라, 같은 재료 · 방향 · 주파수로 만든 다른 시험의 표를 서버가 찾아 주고 사람이 고른다.
 * 평균은 서버가 낸다 — 고른 방식(온도 격자 · 온도 모으기 · 모든 시편에 있는 온도만)으로,
 * 줄마다 E′ 변동계수 · 시편 수와 함께.
 */

import { useCallback, useEffect, useState } from 'react'

import { fittingApi } from '@/modules/fitting/api'
import type { components } from '@/shared/api/schema'
import { CurveChart } from '@/modules/tests/CurveChart'
import { viscoelasticApi } from '@/modules/viscoelastic/api'
import type { ModulusCompanion, ModulusTable } from '@/modules/viscoelastic/api'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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
import { axisLabel, display, formatScalar, toDisplay } from '@/shared/units'

type AveragePreview = components['schemas']['DmaTemperaturePreviewOut']

/** 주파수 칸의 단위 — 표(`shared/units`)에서 읽는다. */
const FREQUENCY_UNIT = display('Hz').unit

export function ModulusTableSection({ testRunId }: { testRunId: string }) {
  const [tables, setTables] = useState<ModulusTable[]>([])
  const [selected, setSelected] = useState<ModulusTable | null>(null)
  const [frequency, setFrequency] = useState('1')
  const [label, setLabel] = useState('')
  /**
   * 표 여럿을 어떻게 평균하나(2026-11-14, VOC 48). 짝짓기(±0.5 K · 모든 시편에 짝)는 온도를 올리며
   * 잰 시험이 거의 다 빠져 기본을 격자로 둔다 — 한 온도씩 잰 시험은 합집합.
   */
  const [average, setAverage] = useState<'grid' | 'union' | 'matched'>('grid')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [removing, setRemoving] = useState<ModulusTable | null>(null)
  /** 같이 평균할 수 있는 다른 시험의 표와, 그중 고른 것. 표를 바꾸면 비운다. */
  const [companions, setCompanions] = useState<ModulusCompanion[]>([])
  const [picked, setPicked] = useState<string[]>([])
  /**
   * 시편 평균을 **만들기 전에** 본다(2026-11-15, VOC 48). 전에는 초안 카드를 만들어 다른 탭에서
   * 펼쳐야 평균이 보였다 — 평균 방식을 시험 모양과 안 맞게 고르면 그럴듯하지만 틀린 줄이
   * 생기는데, 그것은 평균한 줄을 봐야만 안다. 계산은 서버가 한다(카드 만들기와 같은 함수).
   */
  const [preview, setPreview] = useState<AveragePreview | null>(null)
  const [previewError, setPreviewError] = useState<Error | null>(null)

  const reload = useCallback(async () => {
    const found = await viscoelasticApi.modulusTables(testRunId)
    setTables(found)
    setSelected((current) => found.find((one) => one.id === current?.id) ?? found[0] ?? null)
  }, [testRunId])

  useEffect(() => {
    void reload().catch((caught: unknown) =>
      setError(caught instanceof Error ? caught : new Error('불러오지 못했습니다.'))
    )
  }, [reload])

  const selectedId = selected?.id
  useEffect(() => {
    setCompanions([])
    setPicked([])
    if (!selectedId) return
    let cancelled = false
    viscoelasticApi
      .companionTables(selectedId)
      .then((found) => {
        if (!cancelled) setCompanions(found)
      })
      .catch((caught: unknown) => {
        if (!cancelled)
          setError(caught instanceof Error ? caught : new Error('같이 평균할 표를 불러오지 못했습니다.'))
      })
    return () => {
      cancelled = true
    }
  }, [selectedId])

  // 고른 표 · 방식이 바뀌면 다시 계산한다 — 누를 단추를 두면 옛 미리보기를 보고 만든다.
  const pickedKey = picked.join(',')
  useEffect(() => {
    setPreview(null)
    setPreviewError(null)
    if (!selectedId || pickedKey === '') return
    let cancelled = false
    fittingApi
      .previewDmaTemperature({
        modulus_table_ids: [selectedId, ...pickedKey.split(',')],
        average,
        grid_step_k: 1,
      })
      .then((found) => {
        if (!cancelled) setPreview(found)
      })
      .catch((caught: unknown) => {
        if (!cancelled)
          setPreviewError(caught instanceof Error ? caught : new Error('평균을 미리 보지 못했습니다.'))
      })
    return () => {
      cancelled = true
    }
  }, [selectedId, pickedKey, average])

  async function build() {
    const value = Number(frequency)
    if (!Number.isFinite(value) || value <= 0) {
      setError(new Error('주파수는 양수여야 합니다.'))
      return
    }
    setBusy(true)
    setError(null)
    setDone(null)
    try {
      const made = await viscoelasticApi.createModulusTable(testRunId, value)
      await reload()
      setSelected(made)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('표를 만들지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  async function makeCard(table: ModulusTable) {
    setBusy(true)
    setError(null)
    setDone(null)
    try {
      const card = await fittingApi.createDmaTemperature({
        modulus_table_ids: [table.id, ...picked],
        label: label.trim() || defaultLabel(table),
        average,
        grid_step_k: 1,
      })
      setDone(`카드 「${card.label}」 를 만들었습니다 — 재료의 CAE 카드 탭에 있습니다.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('카드를 만들지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  async function remove(table: ModulusTable) {
    setBusy(true)
    setError(null)
    try {
      await viscoelasticApi.removeModulusTable(table.id)
      setRemoving(null)
      setSelected(null)
      await reload()
    } catch (caught) {
      setRemoving(null)
      setError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  function defaultLabel(table: ModulusTable): string {
    const head = `저장 탄성률 ${table.frequency_hz} ${FREQUENCY_UNIT}`
    return picked.length > 0 ? `${head} · 시편 ${picked.length + 1}개 평균` : head
  }

  const points: [number, number][] = (selected?.rows ?? []).map((one) => [
    toDisplay(one.temperature_k, 'K'),
    toDisplay(one.storage_pa, 'Pa'),
  ])

  return (
    <section aria-label="온도별 탄성률 표" className="space-y-2 rounded-md border p-3">
      <div className="flex flex-wrap items-end gap-2">
        <h3 className="mr-auto font-medium">주파수 지정 온도별 E′ 표</h3>
        <div className="space-y-1">
          <Label htmlFor="modulus-frequency" className="text-xs">
            주파수 ({FREQUENCY_UNIT})
          </Label>
          <Input
            id="modulus-frequency"
            className="h-8 w-24"
            inputMode="decimal"
            value={frequency}
            onChange={(event) => setFrequency(event.target.value)}
          />
        </div>
        <Button size="sm" className="h-8" disabled={busy} onClick={() => void build()}>
          표 만들기
        </Button>
      </div>
      <p className="text-muted-foreground text-xs">
        시험의 온도별 곡선에서 고른 주파수의 저장 · 손실 탄성률과 tan δ 를 온도마다 한 줄로
        모읍니다. 온도마다 주파수를 훑은 곡선은 그 주파수로 보간하고, 온도를 올리며 잰 곡선은 그
        주파수의 점을 고릅니다. 잰 범위 밖의 온도는 외삽하지 않고 뺍니다.
      </p>

      <ErrorNotice error={error} />
      {done && <p className="text-sm text-emerald-700 dark:text-emerald-400">{done}</p>}

      {tables.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-muted-foreground text-xs">만든 표</span>
          {tables.map((one) => (
            <Button
              key={one.id}
              size="sm"
              variant={selected?.id === one.id ? 'secondary' : 'ghost'}
              className="h-7 text-xs"
              onClick={() => setSelected(one)}
            >
              {one.frequency_hz} {FREQUENCY_UNIT} · {one.rows.length}온도
            </Button>
          ))}
        </div>
      )}

      {selected && (
        <div className="space-y-2">
          {selected.modulus_basis === 'G' && (
            <Badge variant="outline" className="text-xs">
              전단(G′)으로 잰 표 — 카드에는 E = 2(1+ν)G 로 옮겨 담습니다
            </Badge>
          )}
          <CurveChart
            points={points}
            pointsLabel="저장 탄성률"
            xLabel={axisLabel('온도', 'K')}
            yLabel={axisLabel(selected.modulus_basis === 'G' ? '저장 전단 탄성률 G′' : '저장 탄성률 E′', 'Pa')}
            logY
            height={260}
          />
          <div className="rounded-md border">
            <Table className="text-sm">
              <TableHeader>
                <TableRow>
                  <TableHead>온도</TableHead>
                  <TableHead className="text-right">저장 탄성률</TableHead>
                  <TableHead className="text-right">손실 탄성률</TableHead>
                  <TableHead className="text-right">tan δ</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {selected.rows.map((one) => (
                  <TableRow key={one.temperature_k}>
                    <TableCell className="tabular-nums">
                      {formatScalar(one.temperature_k, 'K')}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {formatScalar(one.storage_pa, 'Pa')}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {one.loss_pa == null ? '—' : formatScalar(one.loss_pa, 'Pa')}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {one.tan_delta == null ? '—' : one.tan_delta.toPrecision(3)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {selected.notes.length > 0 && (
            <ul className="text-muted-foreground space-y-0.5 text-xs">
              {selected.notes.map((note) => (
                <li key={note}>· {note}</li>
              ))}
            </ul>
          )}
          <fieldset className="space-y-1">
            <legend className="text-xs font-medium">같이 평균할 다른 시편의 표</legend>
            {companions.length === 0 ? (
              <p className="text-muted-foreground text-xs">
                같은 재료 · 방향 · 주파수({selected.frequency_hz} {FREQUENCY_UNIT})로 만든 다른 시험의
                표가 없습니다. 다른 시편의 시험에서 같은 주파수로 표를 만들면 여기서 골라 평균할 수
                있습니다.
              </p>
            ) : (
              <>
                {companions.map((one) => (
                  <label key={one.id} className="flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      checked={picked.includes(one.id)}
                      onChange={(event) =>
                        setPicked((current) =>
                          event.target.checked
                            ? [...current, one.id]
                            : current.filter((id) => id !== one.id)
                        )
                      }
                    />
                    <span>
                      {one.specimen_name} · {one.record_name} · {one.row_count}온도
                      {one.temperature_min_k != null && one.temperature_max_k != null && (
                        <span className="text-muted-foreground">
                          {' '}
                          ({formatScalar(one.temperature_min_k, 'K')} ~{' '}
                          {formatScalar(one.temperature_max_k, 'K')})
                        </span>
                      )}
                    </span>
                  </label>
                ))}
                <p className="text-muted-foreground text-xs">
                  고르면 온도마다 평균한 카드가 됩니다. 줄마다 E′ 변동계수와 기여 시편 수를 함께
                  둡니다.
                </p>
                <div className="space-y-1">
                  <Label htmlFor="modulus-average" className="text-xs">
                    평균 방식
                  </Label>
                  <select
                    id="modulus-average"
                    className="h-8 rounded border px-2 text-xs"
                    value={average}
                    onChange={(event) => setAverage(event.target.value as typeof average)}
                  >
                    <option value="grid">
                      온도 격자(1 K) — 시편마다 잰 범위 안에서 log E′ 보간(온도를 올리며 잰 시험)
                    </option>
                    <option value="union">온도 모으기 — 한 온도씩 잰 시험(±0.5 K 를 같은 온도로)</option>
                    <option value="matched">모든 시편에 있는 온도만(±0.5 K)</option>
                  </select>
                </div>
              </>
            )}
          </fieldset>
          {picked.length > 0 && (
            <AveragePreviewView preview={preview} error={previewError} basis={selected.modulus_basis} />
          )}
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <Label htmlFor="modulus-card-label" className="text-xs">
                카드 이름
              </Label>
              <Input
                id="modulus-card-label"
                className="h-8 w-64"
                placeholder={defaultLabel(selected)}
                value={label}
                onChange={(event) => setLabel(event.target.value)}
              />
            </div>
            <Button size="sm" className="h-8" disabled={busy} onClick={() => void makeCard(selected)}>
              {picked.length > 0 ? `시편 ${picked.length + 1}개 평균으로 카드 만들기` : '이 표로 카드 만들기'}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="text-destructive h-8"
              disabled={busy}
              onClick={() => setRemoving(selected)}
            >
              이 표 지우기
            </Button>
          </div>
        </div>
      )}
      <ConfirmDialog
        open={removing !== null}
        title="온도별 탄성률 표 지우기"
        body={
          removing
            ? `${removing.frequency_hz} ${FREQUENCY_UNIT} 표(${removing.rows.length}온도)를 지웁니다. 카드가 근거로 든 표면 서버가 막습니다.`
            : ''
        }
        busy={busy}
        onConfirm={() => removing && void remove(removing)}
        onClose={() => setRemoving(null)}
      />
    </section>
  )
}

/**
 * 시편 평균 미리보기 — 평균 곡선 뒤에 시편마다의 곡선을 깔고, 줄마다 몇 시편이 받치는지와 카드
 * 근거에 실릴 메모를 보인다. **확정 전에 볼 것**(보간한 줄 · 로트 섞임)은 따로 세운다.
 */
function AveragePreviewView({
  preview,
  error,
  basis,
}: {
  preview: AveragePreview | null
  error: Error | null
  basis: string
}) {
  if (error) {
    return (
      <div className="space-y-1 rounded-md border p-2">
        <p className="text-xs font-medium">평균 미리보기</p>
        <ErrorNotice error={error} />
      </div>
    )
  }
  if (!preview) {
    return <p className="text-muted-foreground rounded-md border p-2 text-xs">평균을 계산하는 중입니다…</p>
  }
  const mean: [number, number][] = preview.rows.map((one) => [
    toDisplay(one.temperature, 'K'),
    toDisplay(one.storage_modulus, 'Pa'),
  ])
  const counts = Object.entries(preview.rows_by_sample_count)
    .sort(([left], [right]) => Number(right) - Number(left))
    .map(([count, rows]) => `시편 ${count}개 ${rows}줄`)
    .join(' · ')
  const cautions = new Set(preview.cautions)
  const others = preview.notes.filter((note) => !cautions.has(note))
  return (
    <section aria-label="평균 미리보기" className="space-y-2 rounded-md border p-2">
      <p className="text-xs">
        <b>평균 미리보기</b> — 만들면 {preview.rows.length}줄({counts})
        {preview.lot_count > 1 && ` · 시료(로트) ${preview.lot_count}개`}. 카드는 아직 만들지
        않았습니다.
      </p>
      <CurveChart
        points={mean}
        pointsLabel="평균"
        background={preview.tables.map((one) => ({
          points: one.points.map(
            ([temperature, storage]) =>
              [toDisplay(temperature, 'K'), toDisplay(storage, 'Pa')] as [number, number]
          ),
          label: one.specimen_name,
        }))}
        xLabel={axisLabel('온도', 'K')}
        yLabel={axisLabel(basis === 'G' ? '저장 탄성률 E′ (G′ 에서 옮김)' : '저장 탄성률 E′', 'Pa')}
        logY
        height={240}
      />
      {preview.cautions.length > 0 && (
        <ul className="space-y-0.5 rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs">
          {preview.cautions.map((note) => (
            <li key={note}>· {note}</li>
          ))}
        </ul>
      )}
      {others.length > 0 && (
        <ul className="space-y-0.5 text-xs">
          {others.map((note) => (
            <li key={note}>· {note}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
