/**
 * 기록의 「바뀐 것」 — 변경 이력(관리자)과 내 자료 변경 이력(등록자)이 함께 쓴다.
 *
 * **모양이 둘이다.** 고친 일은 `{칸: {before, after}}` 로 바뀐 것만 담기고, 나머지 일은 값 하나를
 * 담는다 — 남의 자료 고침의 근거·건수, 문헌 값의 등급, 이관한 개수. 전에는 앞의 모양만 그려서
 * 뒤의 것이 「없음 → 없음」 으로 보였다(2026-09-25 에 기록이 늘며 드러났다).
 */

import type { AuditEntry } from '@/modules/audit/api'

/** 서버가 싣는 키 가운데 사람 말이 따로 있는 것. 나머지는 키 그대로 보인다. */
const KEY_LABELS: Record<string, string> = {
  basis: '근거',
  count: '건수',
  targets: '대상',
}

function isDiff(value: unknown): value is { before?: unknown; after?: unknown } {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    ('before' in value || 'after' in value)
  )
}

function shown(value: unknown): string {
  if (value === null || value === undefined) return '없음'
  if (Array.isArray(value)) return value.map(shown).join(', ')
  if (typeof value === 'boolean') return value ? '예' : '아니오'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function Changes({ entry }: { entry: AuditEntry }) {
  const changes = (entry.changes ?? {}) as Record<string, unknown>
  const keys = Object.keys(changes)
  if (keys.length === 0) return <span className="text-muted-foreground">—</span>
  return (
    <div className="space-y-0.5">
      {keys.map((key) => {
        const change = changes[key]
        const label = KEY_LABELS[key] ?? key
        return (
          <div key={key} className="text-xs">
            <span className="text-muted-foreground">{label}</span>{' '}
            {isDiff(change) ? (
              <>
                <span className="line-through opacity-60">{shown(change.before)}</span> →{' '}
                <span className="font-medium">{shown(change.after)}</span>
              </>
            ) : (
              <span className="font-medium">{shown(change)}</span>
            )}
          </div>
        )
      })}
    </div>
  )
}
