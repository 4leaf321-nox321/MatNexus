/**
 * 장비 하나 — **정보·부속·교정.**
 *
 * 부속이 따로 있는 이유: 문헌 사양의 「±50kN」 은 모델 것이고, 실제로는 5kN
 * 로드셀이 물려 있을 수 있다. **그 장비로 잰 값의 범위를 정하는 것은 부속이다.**
 *
 * 교정은 **이력이라 덮지 않는다.** 고칠 일이 있으면 한 줄 더 넣는다.
 */

import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { EquipmentForm } from '@/modules/equipment/EquipmentForm'
import {
  CALIBRATION_RESULT_LABELS,
  OWNERSHIP_LABELS,
  PART_KIND_LABELS,
  STATUS_LABELS,
  calibrationState,
  equipmentApi,
} from '@/modules/equipment/api'
import type {
  EquipmentCalibration,
  EquipmentPart,
  EquipmentUnit,
} from '@/modules/equipment/api'
import type { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'

const dash = <span className="text-muted-foreground">—</span>

function Facts({ unit }: { unit: EquipmentUnit }) {
  const org = unit.org
    ? [unit.org.parent_label, unit.org.label].filter(Boolean).join(' › ')
    : null
  const rows: [string, string | null][] = [
    ['자산번호', unit.asset_no],
    ['장비 유형', unit.instrument_type?.label ?? null],
    ['조직', org],
    ['시험실', [unit.lab?.label, unit.location_detail].filter(Boolean).join(' · ') || null],
    ['제조사·모델', [unit.vendor, unit.model].filter(Boolean).join(' ') || null],
    ['시리얼', unit.serial_no],
    ['상태', `${STATUS_LABELS[unit.status] ?? unit.status} · ${OWNERSHIP_LABELS[unit.ownership]}`],
    ['담당자', [unit.owner_name, unit.owner_contact].filter(Boolean).join(' · ') || null],
    ['도입일', unit.commissioned_on],
    ['장비 파일 이름', unit.instrument_term?.label ?? null],
    ['비고', unit.notes],
  ]
  const extra = Object.entries(unit.attributes ?? {})
  return (
    <div className="space-y-3">
      <table className="text-sm">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <td className="text-muted-foreground py-1 pr-4 align-top whitespace-nowrap">
                {label}
              </td>
              <td className="py-1">{value || dash}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {extra.length > 0 && (
        <div className="rounded border p-3">
          <div className="text-muted-foreground mb-1 text-xs">
            장비 유형이 정한 칸
          </div>
          <table className="text-sm">
            <tbody>
              {extra.map(([key, value]) => (
                <tr key={key}>
                  <td className="text-muted-foreground py-1 pr-4">{key}</td>
                  <td className="py-1">{String(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Parts({ unitId }: { unitId: string }) {
  const [rows, setRows] = useState<EquipmentPart[] | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [kind, setKind] = useState('load_cell')
  const [label, setLabel] = useState('')
  const [capacity, setCapacity] = useState('')

  const load = useCallback(() => {
    equipmentApi.parts(unitId).then(setRows).catch((caught) => setError(caught as ApiError | Error))
  }, [unitId])
  useEffect(load, [load])

  async function add() {
    setError(null)
    try {
      await equipmentApi.addPart(unitId, { kind, label, capacity: capacity || null })
      setLabel('')
      setCapacity('')
      load()
    } catch (caught) {
      setError(caught as ApiError | Error)
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-sm">
        <b>실제 측정 범위를 정하는 것이 부속입니다.</b> 카탈로그의 「±50kN」 은 모델
        사양이고, 5kN 로드셀이 물려 있으면 그 장비로 잴 수 있는 것은 5kN 입니다.
      </p>
      {error != null && <ErrorNotice error={error} />}
      <div className="flex flex-wrap items-end gap-2">
        <select
          className="h-9 rounded-md border px-2 text-sm"
          value={kind}
          onChange={(event) => setKind(event.target.value)}
        >
          {Object.entries(PART_KIND_LABELS).map(([key, name]) => (
            <option key={key} value={key}>
              {name}
            </option>
          ))}
        </select>
        <Input
          className="w-56"
          placeholder="이름 (50kN 로드셀)"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
        />
        <Input
          className="w-40"
          placeholder="용량 (50 kN)"
          value={capacity}
          onChange={(event) => setCapacity(event.target.value)}
        />
        <Button onClick={add} disabled={label.trim() === ''}>
          부속 추가
        </Button>
      </div>
      {rows && rows.length === 0 && (
        <p className="text-muted-foreground rounded border border-dashed p-4 text-sm">
          부속이 없습니다.
        </p>
      )}
      {rows && rows.length > 0 && (
        <table className="w-full text-left text-sm">
          <thead className="text-muted-foreground border-b text-xs">
            <tr>
              <th className="py-1 pr-3 font-medium">종류</th>
              <th className="py-1 pr-3 font-medium">이름</th>
              <th className="py-1 pr-3 font-medium">용량</th>
              <th className="py-1 pr-3 font-medium">자산번호</th>
              <th className="py-1" />
            </tr>
          </thead>
          <tbody>
            {rows.map((part) => (
              <tr key={part.id} className="border-b last:border-0">
                <td className="py-2 pr-3">{PART_KIND_LABELS[part.kind] ?? part.kind}</td>
                <td className="py-2 pr-3">{part.label}</td>
                <td className="py-2 pr-3">{part.capacity || dash}</td>
                <td className="py-2 pr-3">{part.asset_no || dash}</td>
                <td className="py-2 text-right">
                  <button
                    className="text-muted-foreground text-xs underline"
                    onClick={async () => {
                      await equipmentApi.removePart(part.id)
                      load()
                    }}
                  >
                    떼기
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function Calibrations({ unitId }: { unitId: string }) {
  const [rows, setRows] = useState<EquipmentCalibration[] | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [performed, setPerformed] = useState('')
  const [until, setUntil] = useState('')
  const [agency, setAgency] = useState('')
  const [certificate, setCertificate] = useState('')

  const load = useCallback(() => {
    equipmentApi.calibrations(unitId).then(setRows).catch((caught) => setError(caught as ApiError | Error))
  }, [unitId])
  useEffect(load, [load])

  async function add() {
    setError(null)
    try {
      await equipmentApi.addCalibration(unitId, {
        performed_on: performed,
        valid_until: until || null,
        agency: agency || null,
        certificate_no: certificate || null,
      })
      setPerformed('')
      setUntil('')
      setAgency('')
      setCertificate('')
      load()
    } catch (caught) {
      setError(caught as ApiError | Error)
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-sm">
        <b>이력이라 덮지 않습니다.</b> 고칠 일이 있으면 한 줄 더 넣습니다. 유효기간을
        모르면 비워 두세요 — <b>빈 칸이 틀린 값보다 낫습니다.</b>
      </p>
      {error != null && <ErrorNotice error={error} />}
      <div className="flex flex-wrap items-end gap-2">
        <Input
          type="date"
          className="w-40"
          value={performed}
          onChange={(event) => setPerformed(event.target.value)}
        />
        <Input
          type="date"
          className="w-40"
          value={until}
          onChange={(event) => setUntil(event.target.value)}
        />
        <Input
          className="w-40"
          placeholder="기관"
          value={agency}
          onChange={(event) => setAgency(event.target.value)}
        />
        <Input
          className="w-44"
          placeholder="성적서 번호"
          value={certificate}
          onChange={(event) => setCertificate(event.target.value)}
        />
        <Button onClick={add} disabled={!performed}>
          교정 기록
        </Button>
      </div>
      {rows && rows.length === 0 && (
        <p className="text-muted-foreground rounded border border-dashed p-4 text-sm">
          교정 기록이 없습니다.
        </p>
      )}
      {rows && rows.length > 0 && (
        <table className="w-full text-left text-sm">
          <thead className="text-muted-foreground border-b text-xs">
            <tr>
              <th className="py-1 pr-3 font-medium">교정일</th>
              <th className="py-1 pr-3 font-medium">유효기간</th>
              <th className="py-1 pr-3 font-medium">기관</th>
              <th className="py-1 pr-3 font-medium">성적서</th>
              <th className="py-1 font-medium">결과</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const state = calibrationState(row.valid_until)
              return (
                <tr key={row.id} className="border-b last:border-0">
                  <td className="py-2 pr-3">{row.performed_on}</td>
                  <td className="py-2 pr-3">
                    {row.valid_until ?? dash}
                    <span className="text-muted-foreground ml-1 text-xs">
                      {state.tone === 'over' || state.tone === 'due' ? state.text : ''}
                    </span>
                  </td>
                  <td className="py-2 pr-3">{row.agency || dash}</td>
                  <td className="py-2 pr-3">{row.certificate_no || dash}</td>
                  <td className="py-2">
                    {CALIBRATION_RESULT_LABELS[row.result] ?? row.result}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default function EquipmentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [unit, setUnit] = useState<EquipmentUnit | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [editing, setEditing] = useState(false)

  useEffect(() => {
    if (!id) return
    equipmentApi.unit(id).then(setUnit).catch((caught) => setError(caught as ApiError | Error))
  }, [id])

  if (error != null) return <ErrorNotice error={error} />
  if (!unit || !id) return null

  return (
    <div className="space-y-4">
      <PageHeader
        title={unit.name}
        description={unit.asset_no ?? '자산번호 없음'}
        actions={
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setEditing((was) => !was)}>
              {editing ? '편집 닫기' : '편집'}
            </Button>
            <Button variant="outline" onClick={() => navigate('/settings/equipment')}>
              목록
            </Button>
          </div>
        }
      />

      {editing ? (
        <EquipmentForm
          unit={unit}
          onDone={(saved) => {
            setUnit(saved)
            setEditing(false)
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <Tabs defaultValue="facts">
          <TabsList>
            <TabsTrigger value="facts">정보</TabsTrigger>
            <TabsTrigger value="parts">
              부속{unit.part_count ? ` ${unit.part_count}` : ''}
            </TabsTrigger>
            <TabsTrigger value="calibration">교정</TabsTrigger>
          </TabsList>
          <TabsContent value="facts" className="mt-3">
            <Facts unit={unit} />
          </TabsContent>
          <TabsContent value="parts" className="mt-3">
            <Parts unitId={id} />
          </TabsContent>
          <TabsContent value="calibration" className="mt-3">
            <Calibrations unitId={id} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}
