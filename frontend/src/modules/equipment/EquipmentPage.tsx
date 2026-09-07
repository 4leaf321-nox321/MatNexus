/**
 * 보유 장비 — **목록이 먼저다.**
 *
 * 사람이 여기 오는 이유가 「그 장비 어디 있지」·「교정 언제 했지」 라서, 현황
 * 요약보다 목록이 위에 선다. 요약은 접어 두고 필요할 때 편다.
 *
 * **얼굴은 장비명이다.** 「생기연 DMA」·「대형 챔버」 로 부르지 자산번호로 부르지
 * 않는다 — 자산번호는 스티커와 대조할 때 쓰므로 작게, 이름 아래 붙인다.
 */

import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { EquipmentBulkDialog } from '@/modules/equipment/EquipmentBulkDialog'
import { EquipmentForm } from '@/modules/equipment/EquipmentForm'
import {
  OWNERSHIP_LABELS,
  STATUS_LABELS,
  calibrationState,
  equipmentApi,
} from '@/modules/equipment/api'
import type { EquipmentSummaryRow, EquipmentUnit } from '@/modules/equipment/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { useResource } from '@/shared/hooks/useResource'

const dash = <span className="text-muted-foreground">—</span>

/** 교정 상태의 색. **「기간 없음」 은 경고색을 안 쓴다** — 모르는 것은 나쁜 것이 아니다. */
const TONES: Record<string, string> = {
  none: 'text-muted-foreground',
  ok: 'text-emerald-700',
  due: 'text-amber-700',
  over: 'text-red-700',
}

function StatusBadge({ value }: { value: string }) {
  const tone =
    value === 'active'
      ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
      : value === 'maintenance'
        ? 'bg-amber-50 text-amber-800 border-amber-200'
        : value === 'retired'
          ? 'bg-neutral-100 text-neutral-600 border-neutral-200'
          : 'bg-sky-50 text-sky-800 border-sky-200'
  return (
    <span className={`rounded border px-1.5 py-0.5 text-xs ${tone}`}>
      {STATUS_LABELS[value] ?? value}
    </span>
  )
}

function SummaryTable({ title, rows }: { title: string; rows: EquipmentSummaryRow[] }) {
  if (rows.length === 0) return null
  return (
    <div className="min-w-56 flex-1">
      <div className="text-muted-foreground mb-1 text-xs font-medium">{title}</div>
      <table className="w-full text-sm">
        <tbody>
          {rows.map((row) => (
            <tr key={`${title}:${row.key}`} className="border-b last:border-0">
              <td className="py-1">{row.label}</td>
              <td className="py-1 text-right tabular-nums">{row.total}</td>
              <td className="py-1 pl-2 text-right text-xs">
                {row.calibration_due > 0 ? (
                  <span className="text-amber-700">교정 {row.calibration_due}</span>
                ) : (
                  dash
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function UnitRow({ unit }: { unit: EquipmentUnit }) {
  const calibration = calibrationState(unit.calibration_valid_until)
  const place = [unit.lab?.label, unit.location_detail].filter(Boolean).join(' · ')
  // 부서 트리의 꼭대기가 있으면 함께 — 「어느 본부의 팀인가」 가 한 줄에서 보인다.
  const org = unit.org
    ? [unit.org.root_label, unit.org.label].filter(Boolean).join(' › ')
    : null
  return (
    <tr className="border-b align-top last:border-0">
      <td className="py-2 pr-3">
        <Link className="font-medium hover:underline" to={`/settings/equipment/${unit.id}`}>
          {unit.name}
        </Link>
        {/* 자산번호는 **부르는 이름이 아니라 대조용**이라 작게 아래 붙인다. */}
        <div className="text-muted-foreground text-xs">
          {unit.asset_no ?? '자산번호 없음'}
        </div>
      </td>
      <td className="py-2 pr-3 text-sm">
        {[unit.vendor, unit.model].filter(Boolean).join(' ') || dash}
      </td>
      <td className="py-2 pr-3 text-sm">{org ?? dash}</td>
      <td className="py-2 pr-3 text-sm">{place || dash}</td>
      <td className="py-2 pr-3">
        <StatusBadge value={unit.status} />
        {unit.ownership === 'external' && (
          <span className="text-muted-foreground ml-1 text-xs">
            {OWNERSHIP_LABELS.external}
          </span>
        )}
      </td>
      <td className={`py-2 pr-3 text-sm ${TONES[calibration.tone]}`}>{calibration.text}</td>
      <td className="text-muted-foreground py-2 text-right text-sm tabular-nums">
        {unit.part_count > 0 ? unit.part_count : dash}
      </td>
    </tr>
  )
}

export default function EquipmentPage() {
  const [params, setParams] = useSearchParams()
  const [typed, setTyped] = useState(params.get('q') ?? '')
  const q = params.get('q') ?? ''
  const status = params.get('status') ?? ''
  const due = params.get('calibration_due') === '1'
  const [open, setOpen] = useState(false)
  /** 지금 무엇을 열어 두었나 — 폼과 붙여넣기는 함께 뜨지 않는다. */
  const [pane, setPane] = useState<'none' | 'form' | 'bulk'>('none')

  const units = useResource(
    () =>
      equipmentApi.units({
        q: q || undefined,
        status: status || undefined,
        calibration_due: due || undefined,
        limit: 100,
      }),
    [q, status, due]
  )
  const summary = useResource(() => equipmentApi.summary(), [])

  function set(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="보유 장비"
        description="우리가 가진 설비 한 대 한 대 — 어디 있고, 언제 교정했는지."
        actions={
          <div className="flex gap-2">
            <Button
              variant={pane === 'form' ? 'secondary' : 'outline'}
              onClick={() => setPane((was) => (was === 'form' ? 'none' : 'form'))}
            >
              장비 추가
            </Button>
            {/* **몇 대인지 모르는 상태에서 세는 일 자체가 이 화면으로 된다.** */}
            <Button
              variant={pane === 'bulk' ? 'secondary' : 'outline'}
              onClick={() => setPane((was) => (was === 'bulk' ? 'none' : 'bulk'))}
            >
              엑셀에서 붙여넣기
            </Button>
          </div>
        }
      />

      {pane === 'form' && (
        <div className="rounded border p-3">
          <EquipmentForm
            unit={null}
            onDone={() => {
              setPane('none')
              units.reload()
            }}
            onCancel={() => setPane('none')}
          />
        </div>
      )}

      {pane === 'bulk' && (
        <div className="rounded border p-3">
          <EquipmentBulkDialog
            onDone={() => {
              setPane('none')
              units.reload()
            }}
          />
        </div>
      )}

      {/* **찾는 한 칸이 먼저다.** 이름은 부분 일치, 자산번호는 어떻게 쳐도 닿는다. */}
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          set('q', typed.trim())
        }}
      >
        <input
          className="w-72 rounded border px-2 py-1 text-sm"
          placeholder="장비명 또는 자산번호"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
        />
        <select
          className="rounded border px-2 py-1 text-sm"
          value={status}
          onChange={(event) => set('status', event.target.value)}
        >
          <option value="">가동 중인 것 전부</option>
          {Object.entries(STATUS_LABELS).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1 text-sm">
          <input
            type="checkbox"
            checked={due}
            onChange={(event) => set('calibration_due', event.target.checked ? '1' : '')}
          />
          교정 임박·만료
        </label>
        <button
          type="button"
          className="text-muted-foreground ml-auto text-sm underline"
          onClick={() => setOpen((was) => !was)}
        >
          {open ? '현황 접기' : '현황 펼치기'}
        </button>
      </form>

      {open && (
        <div className="rounded border p-3">
          {summary.error && <ErrorNotice error={summary.error} />}
          {summary.data && (
            <div className="flex flex-wrap gap-6">
              <SummaryTable title="상위 조직" rows={summary.data.by_root_org} />
              <SummaryTable title="부서" rows={summary.data.by_org} />
              <SummaryTable title="시험실" rows={summary.data.by_lab} />
            </div>
          )}
        </div>
      )}

      {units.error && <ErrorNotice error={units.error} />}
      {units.data && (
        <>
          <div className="text-muted-foreground text-sm">{units.data.total}대</div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[52rem] text-left">
              <thead className="text-muted-foreground border-b text-xs">
                <tr>
                  <th className="py-1 pr-3 font-medium">장비</th>
                  <th className="py-1 pr-3 font-medium">모델</th>
                  <th className="py-1 pr-3 font-medium">조직</th>
                  <th className="py-1 pr-3 font-medium">위치</th>
                  <th className="py-1 pr-3 font-medium">상태</th>
                  <th className="py-1 pr-3 font-medium">교정</th>
                  <th className="py-1 text-right font-medium">부속</th>
                </tr>
              </thead>
              <tbody>
                {units.data.items.map((unit) => (
                  <UnitRow key={unit.id} unit={unit} />
                ))}
              </tbody>
            </table>
          </div>
          {units.data.items.length === 0 && (
            <p className="text-muted-foreground rounded border border-dashed p-4 text-sm">
              장비가 없습니다. 엑셀에 정리된 목록이 있으면 붙여넣기로 한 번에 넣을 수
              있습니다 — 그 화면은 아직 준비 중입니다.
            </p>
          )}
        </>
      )}
    </div>
  )
}
