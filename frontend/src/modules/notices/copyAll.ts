/**
 * 공지 전부를 **글자 하나로** — 게시판의 「내용 전체 복사」 (2026-10-03).
 *
 * 다른 문서 · 메신저 · AI 에 붙여 넣으려면 공지를 하나씩 열어 복사해야 했다. 여기서는 게시판에
 * 보이는 공지를 **보이는 차례 그대로**(최근에 알린 것이 위) 이어 붙인다.
 *
 * ## 본문은 적힌 그대로다
 *
 * `**굵게**` · `` `코드` `` 표기를 떼지 않는다. 화면은 그 둘을 그려 보이지만(`NoticeBody`) 글자로는
 * 그것이 강조의 전부다 — 떼면 무엇이 중요한지가 사라진다. 머리줄(`#` · `##` · `---`)도 같은
 * 마크다운이라, 마크다운을 읽는 곳에 붙이면 그대로 문서가 되고 아닌 곳에서도 읽힌다.
 *
 * ## 번호는 게시판의 번호다
 *
 * 가장 오래된 것이 1 — 표의 번호와 같아야 「12번 공지」 로 서로 가리킬 수 있다.
 */

import { writerOf } from '@/modules/notices/api'
import type { Notice } from '@/modules/notices/api'
import { stamp } from '@/shared/lib/datetime'

export interface CopyScope {
  /** 게시판이 말한 전체 수 — 번호를 이것으로 센다. */
  total: number
  /** 지금 거른 조건. 걸러 모았으면 머리에 적는다 — 「전부」 로 오해하지 않게. */
  q?: string
  unread?: boolean
  /** 모은 때. */
  at: Date
}

/** 한 건의 머리줄 아래 붙는 것 — 누가 · 언제 · 초안 · 팝업. */
function meta(notice: Notice): string {
  const parts = [
    `올린 사람 ${writerOf(notice)}`,
    `올린 날짜 ${stamp(notice.published_at ?? notice.created_at)}`,
  ]
  if (!notice.is_published) parts.push('초안')
  if (notice.is_popup) parts.push('팝업')
  return parts.join(' · ')
}

export function noticesAsText(notices: Notice[], scope: CopyScope): string {
  const filters = [
    scope.q ? `찾기 「${scope.q}」` : null,
    scope.unread ? '안 읽은 것만' : null,
  ].filter(Boolean)
  const head = [
    `# MatNexus 공지 — ${notices.length}건`,
    '',
    [`모은 때 ${stamp(scope.at.toISOString())}`, ...filters].join(' · '),
  ]
  if (notices.length < scope.total) {
    head.push(`전체 ${scope.total}건 중 ${notices.length}건만 모았습니다 — 찾기로 좁혀 나눠 복사하세요.`)
  }
  const blocks = notices.map((notice, at) =>
    [`## ${scope.total - at}. ${notice.title}`, '', meta(notice), '', notice.body.trim()].join('\n')
  )
  return [head.join('\n'), ...blocks].join('\n\n---\n\n') + '\n'
}
