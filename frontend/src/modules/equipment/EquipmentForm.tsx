/**
 * 장비 추가·수정 폼.
 *
 * **기준정보는 이름으로 보낸다.** 피커(`VocabularyField`)가 이름으로 움직이고
 * 서버가 해석해 FK 까지 채운다 — 폼이 id 를 들고 다니지 않는다.
 *
 * **수정은 바뀐 칸만 보낸다.** 전부 보내면 「안 보낸 것」 과 「비운 것」 이 구별되지
 * 않아, 이름만 고쳐 저장할 때마다 나머지가 지워진다(AGENTS.md).
 */

import { useEffect, useState } from 'react'

import { OWNERSHIP_LABELS, STATUS_LABELS, equipmentApi } from '@/modules/equipment/api'
import type { EquipmentUnit } from '@/modules/equipment/api'
import { vocabularyApi } from '@/modules/vocabulary/api'
import { WorkspacePicker } from '@/modules/workspaces/WorkspacePicker'
import { WorkspaceTreeDialog } from '@/modules/workspaces/WorkspaceTreeDialog'
import type { TreeWorkspace } from '@/modules/workspaces/WorkspaceTreeDialog'
import { workspacesApi } from '@/modules/workspaces/api'
import type { SpecimenField } from '@/modules/vocabulary/api'
import { VocabularyField } from '@/modules/vocabulary/VocabularyField'
import type { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

/** 폼이 들고 있는 값. 전부 문자열이다 — 빈 칸과 `null` 을 화면에서 구별하려고. */
interface Draft {
  name: string
  asset_no: string
  ownership: string
  status: string
  instrument_type: string
  instrument: string
  workspace: string
  lab: string
  location_detail: string
  manufacturer: string
  model: string
  serial_no: string
  owner_name: string
  owner_contact: string
  commissioned_on: string
  retired_on: string
  notes: string
}

const EMPTY: Draft = {
  name: '',
  asset_no: '',
  ownership: 'internal',
  status: 'active',
  instrument_type: '',
  instrument: '',
  workspace: '',
  lab: '',
  location_detail: '',
  manufacturer: '',
  model: '',
  serial_no: '',
  owner_name: '',
  owner_contact: '',
  commissioned_on: '',
  retired_on: '',
  notes: '',
}

function draftOf(unit: EquipmentUnit | null): Draft {
  if (!unit) return EMPTY
  return {
    name: unit.name,
    asset_no: unit.asset_no ?? '',
    ownership: unit.ownership,
    status: unit.status,
    instrument_type: unit.instrument_type?.label ?? '',
    instrument: unit.instrument_term?.label ?? '',
    workspace: unit.org?.slug ?? '',
    lab: unit.lab?.label ?? '',
    location_detail: unit.location_detail ?? '',
    manufacturer: unit.manufacturer ?? '',
    model: unit.model ?? '',
    serial_no: unit.serial_no ?? '',
    owner_name: unit.owner_name ?? '',
    owner_contact: unit.owner_contact ?? '',
    commissioned_on: unit.commissioned_on ?? '',
    retired_on: unit.retired_on ?? '',
    notes: unit.notes ?? '',
  }
}

function Text({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
}: {
  label: string
  value: string
  onChange: (next: string) => void
  placeholder?: string
  type?: string
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  )
}

export function EquipmentForm({
  unit,
  onDone,
  onCancel,
}: {
  /** `null` 이면 새로 만든다. */
  unit: EquipmentUnit | null
  onDone: (saved: EquipmentUnit) => void
  onCancel: () => void
}) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(unit))
  const [fields, setFields] = useState<SpecimenField[]>([])
  /** 부서 목록. **여기서 만들지 않는다** — 조직은 권한이 붙는 자리다. */
  const [workspaces, setWorkspaces] = useState<TreeWorkspace[]>([])
  /** 조직도 모달. 이름을 모를 때 훑어 내려가는 길이다. */
  const [tree, setTree] = useState(false)
  const [attributes, setAttributes] = useState<Record<string, string>>({})
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setDraft(draftOf(unit))
    const found = unit?.attributes ?? {}
    setAttributes(
      Object.fromEntries(Object.entries(found).map(([key, value]) => [key, String(value ?? '')]))
    )
  }, [unit])

  useEffect(() => {
    workspacesApi
      .list(true)
      .then((found) => setWorkspaces(found.filter((one) => one.kind === 'org')))
      .catch(() => setWorkspaces([]))
  }, [])

  // **장비 유형이 칸을 정한다.** UTM 에 「승온 속도」 칸이 있으면 안 되고 DSC 에
  // 「제어 방식: 변위」 가 있으면 안 된다 — 무엇을 그릴지는 서버가 안다.
  const typeId = unit?.instrument_type?.id
  useEffect(() => {
    if (!typeId) {
      setFields([])
      return
    }
    let alive = true
    vocabularyApi
      .termFields('instrument_type', typeId)
      .then((found: SpecimenField[]) => {
        if (alive) setFields(found)
      })
      .catch(() => {
        if (alive) setFields([])
      })
    return () => {
      alive = false
    }
  }, [typeId])

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((was) => ({ ...was, [key]: value }))
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const before = draftOf(unit)
      const body: Record<string, unknown> = {}
      for (const key of Object.keys(EMPTY) as (keyof Draft)[]) {
        // 수정에서는 **바뀐 것만** 보낸다. 빈 문자열은 `null` 로 — 화면에서 지운
        // 것과 안 건드린 것이 서버에서 갈려야 한다.
        if (unit && draft[key] === before[key]) continue
        body[key] = draft[key] === '' ? null : draft[key]
      }
      if (!unit) body.name = draft.name
      if (fields.length > 0) {
        body.attributes = Object.fromEntries(
          Object.entries(attributes).filter(([, value]) => value !== '')
        )
      }
      const saved = unit
        ? await equipmentApi.update(unit.id, body)
        : await equipmentApi.create(body)
      onDone(saved)
    } catch (caught) {
      setError(caught as ApiError | Error)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      {error != null && <ErrorNotice error={error} />}

      {tree && (
        <WorkspaceTreeDialog
          workspaces={workspaces}
          value={draft.workspace || null}
          onChange={(next) => set('workspace', next)}
          onClose={() => setTree(false)}
        />
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <Text
          label="장비명 (필수)"
          value={draft.name}
          onChange={(next) => set('name', next)}
          placeholder="생기연 DMA"
        />
        <Text
          label="자산번호"
          value={draft.asset_no}
          onChange={(next) => set('asset_no', next)}
          placeholder="스티커에 적힌 그대로"
        />
      </div>

      {/* **셋을 한 줄에 두면 좁은 화면에서 겹친다.** 피커는 트리거에 고른 값을
          그리므로 최소 너비가 있고, 그것이 세 개면 640px 에서 서로 밀어낸다.
          두 개씩 끊고, 무너지는 지점을 `sm`(640) 이 아니라 `md`(768) 로 늦춘다. */}
      <div className="grid gap-3 md:grid-cols-2">
        <VocabularyField
          slug="instrument_type"
          label="장비 유형"
          value={draft.instrument_type}
          onChange={(next) => set('instrument_type', next)}
        />
        {/* **시험실과 세부 위치는 짝이다.** 방 이름만으로는 큰 시험실에서 못
            찾고, 세부 위치만으로는 어느 방인지 모른다. */}
        <VocabularyField
          slug="lab"
          label="시험실"
          value={draft.lab}
          onChange={(next) => set('lab', next)}
        />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {/* **조직은 부서에서 온다.** 기준정보에 축을 두려다 걷어냈다 — 부서가
            이미 본부→팀 트리이고, 축을 하나 더 두면 같은 조직이 두 목록에 쌓인다.

            **길이 둘이다.** 이름을 알면 검색이 빠르고, 모르면 조직도를 훑는다. */}
        <div className="space-y-1.5">
          <Label>조직 (부서)</Label>
          {/* `min-w-0` 이 없으면 피커가 자기 내용 너비를 고집해 옆 칸을 밀어낸다 —
              flex 자식의 기본 `min-width: auto` 때문이다. */}
          <div className="flex min-w-0 gap-1">
            <WorkspacePicker
              className="min-w-0 flex-1"
              workspaces={workspaces}
              value={draft.workspace || null}
              onChange={(next) => set('workspace', next)}
              placeholder="부서 고르기"
            />
            <Button
              type="button"
              variant="outline"
              className="shrink-0"
              onClick={() => setTree(true)}
            >
              상세
            </Button>
          </div>
        </div>
        {/* **어떻게 적는지를 자리표시가 보여 준다.** 「세부 위치」 라는 이름만으로는
            방 번호를 적는지 층을 적는지 사람마다 다르게 적는다. 기존 관례대로
            `/` 로 여럿 늘어놓고 `…` 로 「이런 식」 을 나타낸다. */}
        <Text
          label="세부 위치"
          value={draft.location_detail}
          onChange={(next) => set('location_detail', next)}
          placeholder="3번 벤치 / 창가 / A열 4번 랙 …"
        />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1.5">
          <Label>상태</Label>
          <select
            className="h-9 w-full rounded-md border px-2 text-sm"
            value={draft.status}
            onChange={(event) => set('status', event.target.value)}
          >
            {Object.entries(STATUS_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label>소속</Label>
          <select
            className="h-9 w-full rounded-md border px-2 text-sm"
            value={draft.ownership}
            onChange={(event) => set('ownership', event.target.value)}
          >
            {Object.entries(OWNERSHIP_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        {/* **재료·시료와 같은 제조사 축이다** — 같은 회사가 재료도 팔고 장비도
            만든다(3M·듀폰). 축을 나누면 같은 이름이 두 목록에 따로 쌓인다.
            기준정보의 「거래처」 가 아니라 「제조사」 인 것도 그래서다. */}
        <VocabularyField
          slug="manufacturer"
          label="제조사"
          value={draft.manufacturer}
          onChange={(next) => set('manufacturer', next)}
        />
        <Text label="모델" value={draft.model} onChange={(next) => set('model', next)} />
        <Text
          label="시리얼"
          value={draft.serial_no}
          onChange={(next) => set('serial_no', next)}
        />
      </div>

      {/* 장비 파일이 적어 주는 이름. **같은 모델 여러 대는 이것으로 안 갈린다** —
          시험을 어느 대가 냈는지는 나중에 사람이 고르는 자리가 필요하다. */}
      <VocabularyField
        slug="instrument"
        label="장비 파일에 적히는 이름"
        value={draft.instrument}
        parentValue={draft.instrument_type || undefined}
        onChange={(next) => set('instrument', next)}
      />

      <div className="grid gap-3 md:grid-cols-3">
        <Text
          label="담당자"
          value={draft.owner_name}
          onChange={(next) => set('owner_name', next)}
        />
        <Text
          label="연락처"
          value={draft.owner_contact}
          onChange={(next) => set('owner_contact', next)}
          placeholder="내선 1234 / 010-… …"
        />
        <Text
          label="도입일"
          type="date"
          value={draft.commissioned_on}
          onChange={(next) => set('commissioned_on', next)}
        />
      </div>

      {/* **폐기일은 폐기일 때만 묻는다.** 늘 보이면 가동 중인 장비 폼에 빈 칸이
          하나 더 있는 셈이고, 그 빈 칸은 「안 적은 것」 인지 「해당 없는 것」 인지
          구별되지 않는다. */}
      {draft.status === 'retired' && (
        <Text
          label="폐기일"
          type="date"
          value={draft.retired_on}
          onChange={(next) => set('retired_on', next)}
        />
      )}

      {/* **유형이 선언한 칸만 그린다.** 자유 JSON 이 되면 같은 것을 사람마다
          다른 키로 적는다. 유형을 아직 안 고른 장비에는 이 절이 안 뜬다. */}
      {fields.length > 0 && (
        <div className="rounded border p-3">
          <div className="text-muted-foreground mb-2 text-xs">
            {draft.instrument_type} 이(가) 갖는 칸
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {fields.map((field) => (
              <Text
                key={field.key}
                label={field.si_unit ? `${field.label} (${field.si_unit})` : field.label}
                value={attributes[field.key] ?? ''}
                onChange={(next) =>
                  setAttributes((was) => ({ ...was, [field.key]: next }))
                }
              />
            ))}
          </div>
        </div>
      )}

      <Text label="비고" value={draft.notes} onChange={(next) => set('notes', next)} />

      <div className="flex gap-2">
        <Button onClick={save} disabled={saving || draft.name.trim() === ''}>
          {saving ? '저장 중…' : unit ? '저장' : '추가'}
        </Button>
        <Button variant="outline" onClick={onCancel}>
          취소
        </Button>
      </div>
    </div>
  )
}
