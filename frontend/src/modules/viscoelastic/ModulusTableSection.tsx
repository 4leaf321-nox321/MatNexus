/**
 * 주파수 지정 온도별 탄성률 표 — **DMA 온도별 E′ 를 잰 물성으로**(2026-10-22, v1.285.0 보고).
 *
 * 전에는 재료에 「적어 둔 값」 으로 출처를 추정이라 적어 넣을 수밖에 없었다. 다온도 파일은 온도마다
 * 곡선이 따로라 처리 단계로는 표가 안 나와, 마스터커브처럼 시험의 곡선 여럿을 읽는다(서버).
 * 표에서 카드(「온도별 저장 탄성률」 블록)를 만든다 — 정적 탄성계수 칸에는 넣지 않는다.
 */

import { useCallback, useEffect, useState } from 'react'

import { fittingApi } from '@/modules/fitting/api'
import { CurveChart } from '@/modules/tests/CurveChart'
import { viscoelasticApi } from '@/modules/viscoelastic/api'
import type { ModulusTable } from '@/modules/viscoelastic/api'
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

/** 주파수 칸의 단위 — 표(`shared/units`)에서 읽는다. */
const FREQUENCY_UNIT = display('Hz').unit

export function ModulusTableSection({ testRunId }: { testRunId: string }) {
  const [tables, setTables] = useState<ModulusTable[]>([])
  const [selected, setSelected] = useState<ModulusTable | null>(null)
  const [frequency, setFrequency] = useState('1')
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [removing, setRemoving] = useState<ModulusTable | null>(null)

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
        modulus_table_id: table.id,
        label: label.trim() || `저장 탄성률 ${table.frequency_hz} ${FREQUENCY_UNIT}`,
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
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <Label htmlFor="modulus-card-label" className="text-xs">
                카드 이름
              </Label>
              <Input
                id="modulus-card-label"
                className="h-8 w-64"
                placeholder={`저장 탄성률 ${selected.frequency_hz} ${FREQUENCY_UNIT}`}
                value={label}
                onChange={(event) => setLabel(event.target.value)}
              />
            </div>
            <Button size="sm" className="h-8" disabled={busy} onClick={() => void makeCard(selected)}>
              이 표로 카드 만들기
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
