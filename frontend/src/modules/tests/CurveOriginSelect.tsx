/**
 * 곡선 출처 고르기 — 실측 · 그림에서 읽음 · 덱 카드에서 복원 · 합성(2026-11-17, ADR 0096).
 *
 * 덱 카드(소성 표)에서 복원한 곡선이 시험으로 올라와 실측처럼 쓰였다. 출처를 적는 칸이 없었다.
 * **막지 않는다** — 실측이 아니면 카드 근거 · 덱 머리 · 시험 화면에 그렇다고 선다.
 */
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'

/** 곡선 출처 — 서버 `shared/curve_origins.ORIGINS` 와 같은 표. 이 파일에 둔다 — 시험 API 를 흉내 내는
 *  화면 시험이 상수까지 지우지 않게. */
const CURVE_ORIGINS: Record<string, string> = {
  measured: '실측',
  digitized: '그림에서 읽음(디지타이즈)',
  deck_restored: '해석 덱 카드에서 복원',
  synthetic: '식으로 지음(합성)',
}

export function CurveOriginSelect({
  id,
  value,
  onChange,
}: {
  id: string
  value: string
  onChange: (next: string) => void
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>곡선 출처</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Object.entries(CURVE_ORIGINS).map(([key, label]) => (
            <SelectItem key={key} value={key}>
              {label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {value !== 'measured' && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          잰 곡선이 아님 — 이 시험의 값은 카드 근거 · 덱 머리에 「실측이 아닌 곡선」 으로 표시됩니다.
        </p>
      )}
    </div>
  )
}
