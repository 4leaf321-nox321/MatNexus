/**
 * VOC 여러 건을 **글자 하나로** — 게시판의 「내용 복사」 (2026-11-07).
 *
 * 다른 문서 · 메신저 · AI 에 붙이려면 건마다 열어 본문과 이력을 따로 복사해야 했다. 공지의 같은
 * 기능(`notices/copyAll`)과 짜임을 맞춘다 — `#` 머리 · 건마다 `## 번호. 제목` · `---` 구분.
 *
 * ## 번호는 게시판의 번호다
 *
 * 공지와 달리 VOC 는 번호가 저장돼 있다(`seq`). 그대로 쓴다 — 「VOC 12번」 으로 서로 가리킨다.
 *
 * ## 이력은 등록을 뺀다
 *
 * 등록 줄은 「올린 사람 · 올린 날짜」 와 같은 말이다. 옮김과 댓글만 시간순으로 적고, 말은 줄 아래
 * 들여 적는다 — 여러 줄이어도 목록이 안 깨진다.
 *
 * ## 무엇을 모았는지 머리에 적는다
 *
 * 고른 것인지 번호 범위인지, 거른 조건이 무엇인지. 붙여 넣은 쪽에서 「이게 전부인가」 를 알 길이
 * 그것뿐이다.
 */

import type { VocContent, VocEvent } from '@/modules/voc/api'
import { stamp } from '@/shared/lib/datetime'

export interface VocCopyScope {
  /** 찾아야 했던 수 — 고른 수, 또는 범위에 걸린 수. 모은 것이 이보다 적으면 그렇다고 적는다. */
  total: number
  /** 고른 건을 모았나. 아니면 번호 범위(와 거른 조건)다. */
  picked?: boolean
  seqFrom?: number
  seqTo?: number
  /** 지금 거른 조건 — 범위로 모을 때만 걸린다. */
  statusLabel?: string
  q?: string
  mine?: boolean
  /** 모은 때. */
  at: Date
}

/** 번호 범위를 사람 말로. 한쪽이 비면 「부터」 · 「까지」. */
export function rangeLabel(from?: number, to?: number): string | null {
  if (from && to) return from === to ? `번호 ${from}` : `번호 ${from}~${to}`
  if (from) return `번호 ${from}부터`
  if (to) return `번호 ${to}까지`
  return null
}

function scopeLine(scope: VocCopyScope, count: number): string[] {
  const parts = [`모은 때 ${stamp(scope.at.toISOString())}`]
  if (scope.picked) {
    parts.push(`고른 ${scope.total}건`)
  } else {
    const range = rangeLabel(scope.seqFrom, scope.seqTo)
    if (range) parts.push(range)
    if (scope.statusLabel) parts.push(`상태 「${scope.statusLabel}」`)
    if (scope.q) parts.push(`찾기 「${scope.q}」`)
    if (scope.mine) parts.push('내가 낸 것만')
  }
  const lines = [parts.join(' · ')]
  if (count < scope.total) {
    lines.push(
      scope.picked
        ? `고른 ${scope.total}건 중 ${count}건만 찾았습니다 — 나머지는 그 사이 지워졌습니다.`
        : `전체 ${scope.total}건 중 ${count}건만 모았습니다 — 번호 범위로 좁혀 나눠 복사하세요.`
    )
  }
  return lines
}

/** 한 건의 머리줄 아래 붙는 것 — 상태 · 누가 · 언제 · 어느 화면 · 첨부. */
function meta(item: VocContent): string {
  const parts = [
    `상태 ${item.status_label}`,
    `올린 사람 ${item.created_by ?? '알 수 없음'}`,
    `올린 날짜 ${stamp(item.created_at)}`,
  ]
  if (item.page_path) parts.push(`화면 ${item.page_path}`)
  if (item.attachments.length > 0) parts.push(`첨부 ${item.attachments.join(', ')}`)
  return parts.join(' · ')
}

/** 이력 한 줄 — 상세 화면과 같은 말(「접수 로 옮김」 · 「댓글」). 말은 아래에 들여 적는다. */
function eventLine(event: VocEvent): string {
  const what =
    event.from_status !== event.to_status ? `${event.to_status_label} 로 옮김` : '댓글'
  const head = `- ${stamp(event.at)} · ${event.by ?? '알 수 없음'} · ${what}`
  const note = (event.note ?? '').trim()
  if (!note) return head
  return [head, ...note.split('\n').map((line) => (line.trim() ? `  ${line}` : ''))].join('\n')
}

function block(item: VocContent): string {
  const parts = [`## ${item.seq}. ${item.title}`, '', meta(item), '', item.body.trim()]
  // 등록 줄은 머리줄의 「올린 사람 · 올린 날짜」 와 같은 말이라 뺀다.
  const events = item.events.filter((one) => one.from_status !== null)
  if (events.length > 0) parts.push('', '### 이력', '', ...events.map(eventLine))
  return parts.join('\n')
}

export function vocAsText(items: VocContent[], scope: VocCopyScope): string {
  const head = [`# MatNexus VOC — ${items.length}건`, '', ...scopeLine(scope, items.length)]
  return [head.join('\n'), ...items.map(block)].join('\n\n---\n\n') + '\n'
}
