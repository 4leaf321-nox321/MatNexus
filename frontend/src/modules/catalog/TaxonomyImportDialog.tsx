/**
 * 물성 분류 밀어 넣기 — **붙여 넣고, 미리 보고, 넣는다** (ADR 0054).
 *
 * 분류는 바깥(Standard Platform)에 이미 있다 — 그 데이터를 표로 내려받아 엑셀에서 복사해
 * 붙인다. 한 줄이 분야 › 물성군 › 물성 한 갈래다. 없는 분야 · 군은 만들고, 물성은 군에 넣는다.
 *
 * ## 미리 보기가 먼저다
 *
 * 무엇이 새로 생기고 어디서 어디로 옮겨지는지 보고 나서 넣는다. 분야 이름이 한 글자만 달라도
 * 「새 분야」 가 생긴다 — 이 화면의 가장 흔한 사고라서, 새로 생기는 분야 · 군을 맨 위에 둔다.
 * 표를 고치면 미리 보기는 버린다(본 것과 넣는 것이 달라지지 않게).
 *
 * ## 오류가 한 줄이라도 있으면 아무것도 안 들어간다
 *
 * 서버가 그렇게 막는다. 분류가 반만 들어가면 어디까지 들어갔는지를 사람이 다시 맞춰 봐야 한다.
 * 물성은 키 · 이름 · 별칭이 **정확히 하나**에 맞아야 한다 — 비슷한 것을 골라 주지 않는다.
 *
 * ## 줄 번호는 표의 줄 번호다
 *
 * 중간의 빈 줄도 함께 보낸다(서버는 건너뛰되 센다). 빼고 보내면 「3번 줄 오류」 가 표의 다른
 * 줄을 가리킨다.
 */

import { useState } from 'react'
import { ListRestart } from 'lucide-react'

import { DOMAIN_LABELS } from '@/modules/catalog/api'
import { ACTION_LABELS, taxonomyApi } from '@/modules/catalog/taxonomyApi'
import type { Taxonomy, TaxonomyImportResult } from '@/modules/catalog/taxonomyApi'
import { BLANK, COLUMNS, payloadOf, rowsOf } from '@/modules/catalog/taxonomyRows'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PasteGrid } from '@/shared/components/PasteGrid'
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

function count(items: { action: string }[], action: string): number {
  return items.filter((one) => one.action === action).length
}

export function TaxonomyImportDialog({
  tree,
  onClose,
  onApplied,
}: {
  tree: Taxonomy
  onClose: () => void
  onApplied: () => void
}) {
  const [rows, setRows] = useState<string[][]>(() => [BLANK(), BLANK(), BLANK()])
  const [result, setResult] = useState<TaxonomyImportResult | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)

  function edit(next: string[][]) {
    setRows(next)
    // 본 것과 넣는 것이 달라지지 않게 — 표를 고치면 미리 보기를 버린다.
    setResult(null)
  }

  async function send(dryRun: boolean) {
    setBusy(true)
    setError(null)
    try {
      const got = await taxonomyApi.importRows(payloadOf(rows), dryRun)
      setResult(got)
      if (!dryRun) {
        onApplied()
        onClose()
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('넣지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const filled = payloadOf(rows).some((row) => Object.keys(row).length > 0)
  const changes = result
    ? [...result.fields, ...result.groups, ...result.members].filter(
        (one) => one.action !== 'unchanged'
      ).length
    : 0

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>물성 분류 밀어 넣기</DialogTitle>
          <DialogDescription>
            엑셀에서 분야 · 물성군 · 물성 세 열을 복사해 붙여 넣으세요. 없는 분야 · 물성군은
            만들고, 물성은 그 군으로 넣습니다(다른 군에 있던 것은 옮겨집니다). 적지 않은 것은
            그대로 둡니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={error} />

        <PasteGrid
          columns={COLUMNS}
          rows={rows}
          onRows={edit}
          header={
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => edit([...rowsOf(tree), BLANK()])}
              >
                <ListRestart className="size-4" />
                지금 분류 불러오기
              </Button>
              <span className="text-muted-foreground text-xs">
                불러와서 복사하면 엑셀에서 고친 뒤 다시 붙일 수 있습니다.
              </span>
            </div>
          }
        />

        {result && <Plan result={result} tree={tree} />}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
          <Button variant="outline" disabled={busy || !filled} onClick={() => void send(true)}>
            미리 보기
          </Button>
          <Button
            disabled={busy || !result || result.errors.length > 0 || changes === 0}
            onClick={() => void send(false)}
          >
            {result && changes > 0 ? `넣기 (${changes}건)` : '넣기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** 미리 보기 — 새로 생기는 것 · 옮겨지는 것 · 오류를 먼저. 「그대로」 는 수만 센다. */
function Plan({ result, tree }: { result: TaxonomyImportResult; tree: Taxonomy }) {
  const fieldName = new Map([
    ...tree.fields.map((one) => [one.key, one.name] as const),
    ...result.fields.map((one) => [one.key, one.name] as const),
  ])
  const groupName = new Map([
    ...tree.groups.map((one) => [one.key, one.name] as const),
    ...result.groups.map((one) => [one.key, one.name] as const),
  ])
  const newFields = result.fields.filter((one) => one.action === 'create')
  const changedFields = result.fields.filter((one) => ['update', 'restore'].includes(one.action))
  const newGroups = result.groups.filter((one) => one.action === 'create')
  const changedGroups = result.groups.filter((one) =>
    ['update', 'move', 'restore'].includes(one.action)
  )
  const moved = result.members.filter((one) => one.action === 'move')
  // 이름이 정확히 맞아도 뜻이 다를 수 있다 — 「항복응력」 은 유변학 물성이다(ADR 0054).
  const cross = result.members.filter((one) => one.cross_domain && one.action !== 'unchanged')

  return (
    <section className="space-y-3 rounded-md border p-3 text-sm" aria-label="미리 보기">
      <p>
        분야 새로 {newFields.length} · 고침 {changedFields.length} / 물성군 새로 {newGroups.length} ·
        고침 · 옮김 {changedGroups.length} / 물성 넣음 {count(result.members, 'assign')} · 옮김{' '}
        {moved.length} · 그대로 {count(result.members, 'unchanged')}
      </p>

      {result.errors.length > 0 && (
        <div className="border-destructive/50 rounded-md border p-2" role="alert">
          <p className="text-destructive mb-1 font-medium">
            넣을 수 없는 줄 {result.errors.length}개 — 고치기 전에는 아무것도 안 들어갑니다
          </p>
          <ul className="space-y-0.5">
            {result.errors.slice(0, 50).map((one) => (
              <li key={`${one.row}-${one.message}`}>
                {one.row}번 줄 — {one.message}
              </li>
            ))}
            {result.errors.length > 50 && <li>외 {result.errors.length - 50}줄</li>}
          </ul>
        </div>
      )}

      {cross.length > 0 && (
        <div className="rounded-md border border-amber-500/40 p-2" aria-label="다른 분야의 물성">
          <p className="mb-1 font-medium">
            키 앞머리와 다른 분야로 가는 물성 {cross.length} — 이름이 같아도 뜻이 다를 수 있습니다
          </p>
          <ul>
            {cross.slice(0, 50).map((one) => {
              const group = result.groups.find((item) => item.key === one.group_key)
              return (
                <li key={one.property_key}>
                  {one.property_name} ({one.property_key}) — {DOMAIN_LABELS[one.domain] ?? one.domain}{' '}
                  물성 → {fieldName.get(group?.field_key ?? '') ?? group?.field_key} ›{' '}
                  {groupName.get(one.group_key) ?? one.group_key}
                </li>
              )
            })}
            {cross.length > 50 && <li>외 {cross.length - 50}개</li>}
          </ul>
        </div>
      )}

      {newFields.length > 0 && (
        <div>
          <p className="mb-1 font-medium">새로 생기는 분야 — 이름이 기존 분야와 다르지 않은지 보세요</p>
          <div className="flex flex-wrap gap-1.5">
            {newFields.map((one) => (
              <Badge key={one.key} variant="outline">
                {one.name} · {one.key}
              </Badge>
            ))}
          </div>
        </div>
      )}
      {changedFields.length > 0 && (
        <ul>
          {changedFields.map((one) => (
            <li key={one.key}>
              분야 {one.before_name ?? one.name} → {one.name} ({ACTION_LABELS[one.action]})
            </li>
          ))}
        </ul>
      )}
      {newGroups.length > 0 && (
        <div>
          <p className="mb-1 font-medium">새로 생기는 물성군 {newGroups.length}</p>
          <div className="flex flex-wrap gap-1.5">
            {newGroups.slice(0, 80).map((one) => (
              <Badge key={one.key} variant="outline">
                {fieldName.get(one.field_key) ?? one.field_key} › {one.name}
              </Badge>
            ))}
            {newGroups.length > 80 && <span>외 {newGroups.length - 80}개</span>}
          </div>
        </div>
      )}
      {changedGroups.length > 0 && (
        <ul>
          {changedGroups.map((one) => (
            <li key={one.key}>
              물성군 {one.before_name ?? one.name}
              {one.before_name ? ` → ${one.name}` : ''}
              {one.before_field_key
                ? ` — ${fieldName.get(one.before_field_key) ?? one.before_field_key} 에서 ${
                    fieldName.get(one.field_key) ?? one.field_key
                  } 로`
                : ''}{' '}
              ({ACTION_LABELS[one.action]})
            </li>
          ))}
        </ul>
      )}
      {moved.length > 0 && (
        <div>
          <p className="mb-1 font-medium">다른 군에서 옮겨지는 물성 {moved.length}</p>
          <ul>
            {moved.slice(0, 50).map((one) => (
              <li key={one.property_key}>
                {one.property_name} —{' '}
                {groupName.get(one.before_group_key ?? '') ?? one.before_group_key} →{' '}
                {groupName.get(one.group_key) ?? one.group_key}
              </li>
            ))}
            {moved.length > 50 && <li>외 {moved.length - 50}개</li>}
          </ul>
        </div>
      )}
    </section>
  )
}
