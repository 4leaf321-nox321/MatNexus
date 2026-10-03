/**
 * 물성 분류 — **분야 ⊃ 물성군 ⊃ 물성** (ADR 0054, 2026-10-03).
 *
 * 문헌 물성 정의는 키 앞머리(`mechanical.` …)로 열두 갈래로만 나뉘어 있었다. 기계 104종이 한
 * 줄로 늘어서 「강도 계열」 을 고를 길이 없었다. 여기서 분야 아래에 물성군을 세우고 물성을
 * 넣는다. 바깥(Standard Platform)은 이 분류 그대로 물성 목록을 읽어 간다.
 *
 * ## 보기는 누구나, 고치기는 자료 관리자
 *
 * 분류는 전사 자산이다 — 정의문 고치기와 같은 판정(서버가 막는다). 화면은 그 판정을 미리 보여
 * 단추를 감출 뿐이다.
 *
 * ## 고르고 → 넣는다
 *
 * 물성마다 「어느 군?」 을 고르게 하면 271번을 고른다. 체크로 여럿을 고르고 아래 줄에서 군을
 * 한 번 고른다. 다른 군에 있던 것은 옮겨진다 — 물성은 한 군에만 든다(서버가 지킨다).
 *
 * ## 지우는 단추가 없다
 *
 * 분야 · 군은 바깥이 키로 잇는다. 지우면 그쪽에서 행이 말없이 사라진다 — 폐기만 있고, 폐기한
 * 것은 「폐기한 것도 보기」 로 다시 보고 되살린다.
 */

import { useMemo, useState } from 'react'
import { Archive, ArchiveRestore, FolderPlus, Pencil, Plus, Upload } from 'lucide-react'

import { DOMAIN_LABELS, systemUnit } from '@/modules/catalog/api'
import { TaxonomyImportDialog } from '@/modules/catalog/TaxonomyImportDialog'
import { taxonomyApi } from '@/modules/catalog/taxonomyApi'
import type {
  Taxonomy,
  TaxonomyField,
  TaxonomyGroup,
  TaxonomyProperty,
} from '@/modules/catalog/taxonomyApi'
import { useAuth } from '@/shared/auth/AuthContext'
import { isDataSteward } from '@/shared/auth/roles'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
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
import { Textarea } from '@/shared/components/ui/textarea'
import { useResource } from '@/shared/hooks/useResource'
import { cn } from '@/shared/lib/utils'

const SELECT = 'border-input bg-background h-9 w-full rounded-md border px-2 text-sm'

/** 찾기 — 이름 · 키 · 기호 어디든. */
function matches(property: TaxonomyProperty, needle: string): boolean {
  if (!needle) return true
  return [property.name, property.key, property.symbol ?? ''].some((text) =>
    text.toLowerCase().includes(needle)
  )
}

type Editing =
  | { kind: 'field'; field: TaxonomyField | null }
  | { kind: 'group'; group: TaxonomyGroup | null; fieldKey: string }

export default function CatalogTaxonomyPage() {
  const { user } = useAuth()
  const canEdit = isDataSteward(user)
  const tree = useResource(() => taxonomyApi.tree(), [])
  const [query, setQuery] = useState('')
  const [showRetired, setShowRetired] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [editing, setEditing] = useState<Editing | null>(null)
  const [retiring, setRetiring] = useState<
    { kind: 'field'; item: TaxonomyField } | { kind: 'group'; item: TaxonomyGroup } | null
  >(null)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)

  const data = tree.data
  const needle = query.trim().toLowerCase()

  const byGroup = useMemo(() => {
    const out = new Map<string, TaxonomyProperty[]>()
    for (const property of data?.properties ?? []) {
      if (!property.group_key) continue
      out.set(property.group_key, [...(out.get(property.group_key) ?? []), property])
    }
    return out
  }, [data])
  const unclassified = useMemo(
    () => (data?.properties ?? []).filter((one) => !one.group_key && matches(one, needle)),
    [data, needle]
  )

  function toggle(key: string) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      tree.reload()
      return true
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('처리하지 못했습니다.'))
      return false
    } finally {
      setBusy(false)
    }
  }

  async function assign(groupKey: string | null) {
    const ok = await run(() => taxonomyApi.assign(groupKey, [...selected]))
    if (ok) setSelected(new Set())
  }

  async function retire() {
    if (!retiring) return
    const body = { retired: true }
    const ok = await run(() =>
      retiring.kind === 'field'
        ? taxonomyApi.updateField(retiring.item.key, body)
        : taxonomyApi.updateGroup(retiring.item.key, body)
    )
    if (ok) setRetiring(null)
  }

  const classified = (data?.properties ?? []).filter((one) => one.group_key).length
  const fields = (data?.fields ?? []).filter((one) => showRetired || !one.retired)

  return (
    <div className="space-y-4 pb-20">
      <PageHeader
        title="물성 분류"
        description="분야 ⊃ 물성군 ⊃ 물성. 물성은 문헌과 사내에서 만든 것 전부이고, 바깥 시스템(Standard Platform)이 이 분류 그대로 물성 목록을 읽어 갑니다."
        actions={
          canEdit && (
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => setImporting(true)}>
                <Upload className="size-4" />
                밀어 넣기
              </Button>
              <Button variant="outline" onClick={() => setEditing({ kind: 'field', field: null })}>
                <Plus className="size-4" />
                분야 추가
              </Button>
            </div>
          )
        }
      />

      <ErrorNotice error={tree.error} />
      <ErrorNotice error={error} />

      {data && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm">
            물성 {data.properties.length.toLocaleString('ko-KR')}종 · 분류됨 {classified} · 미분류{' '}
            {data.properties.length - classified} · 분야 {data.fields.filter((one) => !one.retired).length} ·
            물성군 {data.groups.filter((one) => !one.retired).length}
          </p>
          {data.truncated && <Badge variant="destructive">물성이 너무 많아 일부만 보입니다</Badge>}
          <Input
            className="h-8 w-56"
            aria-label="물성 찾기"
            placeholder="이름 · 키 · 기호로 찾기"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <label className="flex items-center gap-1.5 text-sm">
            <input
              type="checkbox"
              checked={showRetired}
              onChange={(event) => setShowRetired(event.target.checked)}
            />
            폐기한 것도 보기
          </label>
        </div>
      )}

      {data &&
        fields.map((field) => (
          <FieldSection
            key={field.key}
            field={field}
            groups={data.groups.filter(
              (one) => one.field_key === field.key && (showRetired || !one.retired)
            )}
            byGroup={byGroup}
            needle={needle}
            canEdit={canEdit}
            busy={busy}
            selected={selected}
            onToggle={toggle}
            onEditField={() => setEditing({ kind: 'field', field })}
            onAddGroup={() => setEditing({ kind: 'group', group: null, fieldKey: field.key })}
            onEditGroup={(group) => setEditing({ kind: 'group', group, fieldKey: field.key })}
            onRetireField={() => setRetiring({ kind: 'field', item: field })}
            onRetireGroup={(group) => setRetiring({ kind: 'group', item: group })}
            onRestoreField={() => void run(() => taxonomyApi.updateField(field.key, { retired: false }))}
            onRestoreGroup={(group) =>
              void run(() => taxonomyApi.updateGroup(group.key, { retired: false }))
            }
          />
        ))}

      {data && (
        <section className="rounded-lg border p-4" aria-label="미분류">
          <h2 className="mb-1 font-semibold">미분류 {unclassified.length}</h2>
          <p className="text-muted-foreground mb-3 text-sm">
            아직 물성군에 들지 않은 물성 — 키 앞머리로 묶어 보입니다(분류가 아닙니다).
          </p>
          <UnclassifiedList
            properties={unclassified}
            canEdit={canEdit}
            selected={selected}
            onToggle={toggle}
          />
        </section>
      )}

      {canEdit && selected.size > 0 && data && (
        <SelectionBar
          count={selected.size}
          data={data}
          busy={busy}
          onAssign={(groupKey) => void assign(groupKey)}
          onClear={() => setSelected(new Set())}
        />
      )}

      {editing?.kind === 'field' && (
        <FieldDialog
          field={editing.field}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            tree.reload()
          }}
        />
      )}
      {editing?.kind === 'group' && data && (
        <GroupDialog
          group={editing.group}
          fieldKey={editing.fieldKey}
          fields={data.fields.filter((one) => !one.retired)}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            tree.reload()
          }}
        />
      )}
      <ConfirmDialog
        open={retiring !== null}
        title={retiring?.kind === 'field' ? '분야 폐기' : '물성군 폐기'}
        confirmLabel="폐기"
        busy={busy}
        body={
          retiring && (
            <>
              「{retiring.item.name}」({retiring.item.key}) 을 폐기합니다. 지우지 않습니다 — 바깥
              시스템에는 「쓰지 않음」 으로 남고, 「폐기한 것도 보기」 에서 되살릴 수 있습니다.
            </>
          )
        }
        onConfirm={() => void retire()}
        onClose={() => setRetiring(null)}
      />
      {importing && data && (
        <TaxonomyImportDialog
          tree={data}
          onClose={() => setImporting(false)}
          onApplied={() => tree.reload()}
        />
      )}
    </div>
  )
}

function FieldSection({
  field,
  groups,
  byGroup,
  needle,
  canEdit,
  busy,
  selected,
  onToggle,
  onEditField,
  onAddGroup,
  onEditGroup,
  onRetireField,
  onRetireGroup,
  onRestoreField,
  onRestoreGroup,
}: {
  field: TaxonomyField
  groups: TaxonomyGroup[]
  byGroup: Map<string, TaxonomyProperty[]>
  needle: string
  canEdit: boolean
  busy: boolean
  selected: Set<string>
  onToggle: (key: string) => void
  onEditField: () => void
  onAddGroup: () => void
  onEditGroup: (group: TaxonomyGroup) => void
  onRetireField: () => void
  onRetireGroup: (group: TaxonomyGroup) => void
  onRestoreField: () => void
  onRestoreGroup: (group: TaxonomyGroup) => void
}) {
  // 찾는 중이면 걸린 것이 있는 군만 — 군 이름이 걸리면 그 군의 물성은 다 보인다.
  const shown = groups
    .map((group) => {
      const inside = byGroup.get(group.key) ?? []
      const hit = !needle || group.name.toLowerCase().includes(needle)
      return { group, properties: hit ? inside : inside.filter((one) => matches(one, needle)), hit }
    })
    .filter((one) => !needle || one.hit || one.properties.length > 0)
  if (needle && shown.length === 0 && !field.name.toLowerCase().includes(needle)) return null

  return (
    <section
      className={cn('rounded-lg border p-4', field.retired && 'border-dashed')}
      aria-label={`분야 ${field.name}`}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="font-semibold">{field.name}</h2>
        <code className="text-muted-foreground font-mono text-xs">{field.key}</code>
        {field.retired && <Badge variant="outline">폐기</Badge>}
        <span className="text-muted-foreground text-sm">
          물성군 {field.group_count} · 물성 {field.property_count}
        </span>
        {canEdit && (
          <div className="ml-auto flex gap-1">
            {field.retired ? (
              <Button size="sm" variant="ghost" disabled={busy} onClick={onRestoreField}>
                <ArchiveRestore className="size-4" />
                되살리기
              </Button>
            ) : (
              <>
                <Button size="sm" variant="ghost" onClick={onAddGroup}>
                  <FolderPlus className="size-4" />
                  물성군 추가
                </Button>
                <Button size="sm" variant="ghost" aria-label={`분야 ${field.name} 고치기`} onClick={onEditField}>
                  <Pencil className="size-4" />
                </Button>
                <Button size="sm" variant="ghost" aria-label={`분야 ${field.name} 폐기`} onClick={onRetireField}>
                  <Archive className="size-4" />
                </Button>
              </>
            )}
          </div>
        )}
      </div>
      {field.description && <p className="text-muted-foreground mb-3 text-sm">{field.description}</p>}

      {shown.length === 0 ? (
        <p className="text-muted-foreground text-sm">물성군이 없습니다.</p>
      ) : (
        <div className="space-y-3">
          {shown.map(({ group, properties }) => (
            <section
              key={group.key}
              className={cn('rounded-md border p-3', group.retired && 'border-dashed')}
              aria-label={`물성군 ${group.name}`}
            >
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-medium">{group.name}</h3>
                <code className="text-muted-foreground font-mono text-xs">{group.key}</code>
                {group.retired && <Badge variant="outline">폐기</Badge>}
                <span className="text-muted-foreground text-xs">{group.property_count}종</span>
                {canEdit && (
                  <div className="ml-auto flex gap-1">
                    {group.retired ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => onRestoreGroup(group)}
                      >
                        <ArchiveRestore className="size-4" />
                        되살리기
                      </Button>
                    ) : (
                      <>
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label={`물성군 ${group.name} 고치기`}
                          onClick={() => onEditGroup(group)}
                        >
                          <Pencil className="size-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label={`물성군 ${group.name} 폐기`}
                          onClick={() => onRetireGroup(group)}
                        >
                          <Archive className="size-4" />
                        </Button>
                      </>
                    )}
                  </div>
                )}
              </div>
              {group.description && (
                <p className="text-muted-foreground mb-2 text-xs">{group.description}</p>
              )}
              {properties.length === 0 ? (
                <p className="text-muted-foreground text-xs">든 물성이 없습니다.</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {properties.map((property) => (
                    <PropertyChip
                      key={property.key}
                      property={property}
                      canEdit={canEdit}
                      checked={selected.has(property.key)}
                      onToggle={onToggle}
                      // 씨앗 분야(키 = 키 앞머리)인데 앞머리가 다르면 세워 보인다 — 맞게 둔
                      // 것일 수도 있지만, 「항복응력」 처럼 이름만 맞춰 잘못 든 것일 수도 있다.
                      crossDomain={field.key in DOMAIN_LABELS && property.domain !== field.key}
                    />
                  ))}
                </div>
              )}
            </section>
          ))}
        </div>
      )}
    </section>
  )
}

/** 물성 하나. 자료 관리자에게는 고르는 칸이 붙는다. */
function PropertyChip({
  property,
  canEdit,
  checked,
  onToggle,
  crossDomain = false,
}: {
  property: TaxonomyProperty
  canEdit: boolean
  checked: boolean
  onToggle: (key: string) => void
  crossDomain?: boolean
}) {
  const body = (
    <>
      <span className={cn(property.deprecated && 'line-through')}>{property.name}</span>
      {property.si_unit && (
        <span className="text-muted-foreground">({systemUnit(property.si_unit)})</span>
      )}
      <code className="text-muted-foreground font-mono">{property.key}</code>
      {property.local && <Badge variant="outline">사내</Badge>}
      {crossDomain && (
        <Badge variant="outline" title="키 앞머리가 이 분야와 다릅니다">
          키: {DOMAIN_LABELS[property.domain] ?? property.domain}
        </Badge>
      )}
      {property.deprecated && <Badge variant="outline">폐기</Badge>}
    </>
  )
  const style = cn(
    'inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs',
    checked && 'border-primary bg-primary/10'
  )
  if (!canEdit) return <span className={style}>{body}</span>
  return (
    <label className={cn(style, 'cursor-pointer')} title={`값 ${property.value_count}건`}>
      <input
        type="checkbox"
        aria-label={`${property.name} 고르기`}
        checked={checked}
        onChange={() => onToggle(property.key)}
      />
      {body}
    </label>
  )
}

function UnclassifiedList({
  properties,
  canEdit,
  selected,
  onToggle,
}: {
  properties: TaxonomyProperty[]
  canEdit: boolean
  selected: Set<string>
  onToggle: (key: string) => void
}) {
  const byDomain = new Map<string, TaxonomyProperty[]>()
  for (const property of properties) {
    byDomain.set(property.domain, [...(byDomain.get(property.domain) ?? []), property])
  }
  if (properties.length === 0) {
    return <p className="text-muted-foreground text-sm">모든 물성이 분류됐습니다.</p>
  }
  return (
    <div className="space-y-3">
      {[...byDomain.entries()].map(([domain, rows]) => (
        <div key={domain}>
          <p className="mb-1.5 text-xs font-medium">
            {DOMAIN_LABELS[domain] ?? domain} <span className="text-muted-foreground">{rows.length}</span>
          </p>
          <div className="flex flex-wrap gap-1.5">
            {rows.map((property) => (
              <PropertyChip
                key={property.key}
                property={property}
                canEdit={canEdit}
                checked={selected.has(property.key)}
                onToggle={onToggle}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/** 고른 물성을 한 군에 넣거나 군에서 뺀다 — 화면 아래에 붙는다. */
function SelectionBar({
  count,
  data,
  busy,
  onAssign,
  onClear,
}: {
  count: number
  data: Taxonomy
  busy: boolean
  onAssign: (groupKey: string | null) => void
  onClear: () => void
}) {
  const [target, setTarget] = useState('')
  const fieldName = new Map(data.fields.map((one) => [one.key, one.name]))
  const groups = data.groups.filter((one) => !one.retired)
  return (
    <div className="bg-background fixed inset-x-0 bottom-0 z-20 border-t p-3 shadow-lg">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{count}개 고름</span>
        <select
          aria-label="넣을 물성군"
          className={cn(SELECT, 'w-72')}
          value={target}
          onChange={(event) => setTarget(event.target.value)}
        >
          <option value="">물성군 고르기…</option>
          {groups.map((group) => (
            <option key={group.key} value={group.key}>
              {fieldName.get(group.field_key) ?? group.field_key} › {group.name}
            </option>
          ))}
        </select>
        <Button disabled={busy || !target} onClick={() => onAssign(target)}>
          넣기
        </Button>
        <Button variant="outline" disabled={busy} onClick={() => onAssign(null)}>
          군에서 빼기
        </Button>
        <Button variant="ghost" onClick={onClear}>
          고름 풀기
        </Button>
      </div>
    </div>
  )
}

function FieldDialog({
  field,
  onClose,
  onSaved,
}: {
  field: TaxonomyField | null
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState(field?.name ?? '')
  const [key, setKey] = useState('')
  const [description, setDescription] = useState(field?.description ?? '')
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)

  async function save() {
    setBusy(true)
    setError(null)
    try {
      if (field) {
        await taxonomyApi.updateField(field.key, {
          name: name.trim(),
          // 비우면 지운다 — 빈 글자를 설명으로 남기지 않는다.
          description: description.trim() || null,
        })
      } else {
        await taxonomyApi.createField({
          name: name.trim(),
          key: key.trim() || null,
          description: description.trim() || null,
        })
      }
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{field ? '분야 고치기' : '분야 추가'}</DialogTitle>
          <DialogDescription>
            {field
              ? `키 ${field.key} 는 그대로입니다 — 바깥 시스템이 키로 잇습니다.`
              : '키를 비우면 pf-0001 꼴로 지어 줍니다. 키는 나중에 못 바꿉니다.'}
          </DialogDescription>
        </DialogHeader>
        <ErrorNotice error={error} />
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="taxonomy-field-name">이름</Label>
            <Input
              id="taxonomy-field-name"
              value={name}
              maxLength={100}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          {!field && (
            <div className="space-y-1.5">
              <Label htmlFor="taxonomy-field-key">키 (선택)</Label>
              <Input
                id="taxonomy-field-key"
                value={key}
                maxLength={100}
                placeholder="예: SP 의 분야 키"
                onChange={(event) => setKey(event.target.value)}
              />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="taxonomy-field-description">설명</Label>
            <Textarea
              id="taxonomy-field-description"
              value={description}
              rows={3}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button onClick={save} disabled={busy || !name.trim()}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function GroupDialog({
  group,
  fieldKey,
  fields,
  onClose,
  onSaved,
}: {
  group: TaxonomyGroup | null
  fieldKey: string
  fields: TaxonomyField[]
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState(group?.name ?? '')
  const [key, setKey] = useState('')
  const [field, setField] = useState(fieldKey)
  const [description, setDescription] = useState(group?.description ?? '')
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)

  async function save() {
    setBusy(true)
    setError(null)
    try {
      if (group) {
        await taxonomyApi.updateGroup(group.key, {
          name: name.trim(),
          description: description.trim() || null,
          // 분야를 바꿨을 때만 보낸다 — 안 보낸 칸은 서버가 안 건드린다.
          ...(field !== group.field_key ? { field_key: field } : {}),
        })
      } else {
        await taxonomyApi.createGroup({
          field_key: field,
          name: name.trim(),
          key: key.trim() || null,
          description: description.trim() || null,
        })
      }
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{group ? '물성군 고치기' : '물성군 추가'}</DialogTitle>
          <DialogDescription>
            {group
              ? `키 ${group.key} 는 그대로입니다. 분야를 바꾸면 든 물성이 함께 옮겨 갑니다.`
              : '키를 비우면 pg-0001 꼴로 지어 줍니다. 키는 나중에 못 바꿉니다.'}
          </DialogDescription>
        </DialogHeader>
        <ErrorNotice error={error} />
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="taxonomy-group-field">분야</Label>
            <select
              id="taxonomy-group-field"
              className={SELECT}
              value={field}
              onChange={(event) => setField(event.target.value)}
            >
              {fields.map((one) => (
                <option key={one.key} value={one.key}>
                  {one.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="taxonomy-group-name">이름</Label>
            <Input
              id="taxonomy-group-name"
              value={name}
              maxLength={200}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          {!group && (
            <div className="space-y-1.5">
              <Label htmlFor="taxonomy-group-key">키 (선택)</Label>
              <Input
                id="taxonomy-group-key"
                value={key}
                maxLength={100}
                placeholder="예: SP 의 물성군 키"
                onChange={(event) => setKey(event.target.value)}
              />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="taxonomy-group-description">설명</Label>
            <Textarea
              id="taxonomy-group-description"
              value={description}
              rows={3}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button onClick={save} disabled={busy || !name.trim()}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
