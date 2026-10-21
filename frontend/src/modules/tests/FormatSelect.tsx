/**
 * 읽을 형식(장비 파일 정의) 고르기 — **비우면 자동**(2026-10-20).
 *
 * 사용자 보고: 맞는 형식이 둘 이상인 파일을 자동이 다른 형식으로 골라 곡선 하나로 읽혔고, 올릴
 * 때 고를 방법이 없어 잘못 읽힌 뒤에 「다시 읽기」 를 해야 했다. 올리기 창과 일괄 등록이 함께
 * 쓴다. 고른 형식은 「다시 읽기」 의 고정과 같다 — 다음에 다시 읽어도 그 형식이다.
 *
 * **고를 것이 둘 이상일 때만 선다**(`formatChoices`). 형식이 하나뿐인 종류에서 칸을 늘
 * 띄우면, 고를 일이 없는 사람에게 「무엇을 골라야 하나」 를 묻는 셈이다.
 */

import type { FormatProfile } from '@/modules/tests/api'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'

/** 「자동」 의 값 — 선택 상자는 빈 문자열을 값으로 못 받는다. */
const AUTO = '__auto__'

/** 이 종류에서 고를 수 있는 형식 — 쓰는 중인 것만, 서버가 준 차례(우선순위) 그대로. */
export function formatChoices(profiles: FormatProfile[], testType: string | null): FormatProfile[] {
  return profiles.filter((one) => one.is_active && one.test_type_key === testType)
}

export function FormatSelect({
  choices,
  value,
  onChange,
  id,
  className,
}: {
  choices: FormatProfile[]
  /** 고른 형식 key. `null` 이면 자동. */
  value: string | null
  onChange: (key: string | null) => void
  id?: string
  className?: string
}) {
  return (
    <Select
      value={value ?? AUTO}
      onValueChange={(next) => onChange(next === AUTO ? null : next)}
    >
      <SelectTrigger id={id} className={className} aria-label="읽을 형식">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={AUTO}>자동 (파일 지문으로 고름)</SelectItem>
        {choices.map((one) => (
          <SelectItem key={one.key} value={one.key}>
            {one.label}
            <span className="text-muted-foreground ml-2 font-mono text-xs">{one.key}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
