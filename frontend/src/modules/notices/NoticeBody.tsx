/**
 * 공지 본문 — **줄은 그대로 두고 `**굵게**` 와 `` `코드` `` 만 그린다.**
 *
 * 배포가 싣는 안내(`seeds/notices/*.md`)가 이 두 표기를 쓴다. 그대로 두면 별표와 역따옴표가
 * 글자로 보인다. 그렇다고 마크다운 전부를 그리면 HTML 을 끼워 넣을 길이 생긴다 — 이 두 가지만
 * 글자 조각으로 나눠 그린다(`dangerouslySetInnerHTML` 없이). 줄바꿈·목록 기호(■ · -)는
 * 적힌 그대로가 이미 읽힌다.
 */

import { cn } from '@/shared/lib/utils'

/** 한 줄 안에서만 짝을 찾는다 — 줄을 넘는 `**` 는 강조가 아니라 실수다. */
const TOKEN = /(\*\*[^*\n]+\*\*|`[^`\n]+`)/g

export function NoticeBody({ text, className }: { text: string; className?: string }) {
  return (
    <div className={cn('whitespace-pre-wrap', className)}>
      {text.split(TOKEN).map((part, at) => {
        if (part.length > 4 && part.startsWith('**') && part.endsWith('**')) {
          return <strong key={at}>{part.slice(2, -2)}</strong>
        }
        if (part.length > 2 && part.startsWith('`') && part.endsWith('`')) {
          return (
            <code key={at} className="bg-muted rounded px-1 font-mono text-[0.9em]">
              {part.slice(1, -1)}
            </code>
          )
        }
        return part
      })}
    </div>
  )
}
