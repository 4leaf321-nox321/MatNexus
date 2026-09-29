/**
 * 축 눈금 토글 — **선형 | 로그**. 그래프마다 같은 모양으로 선다(2026-09-29).
 *
 * 곡선 차트 · 분포 상자그림이 함께 쓴다. 로그 눈금을 쓸 수 없는 축(0 이하 값뿐)은
 * 「로그」 를 막고 이유를 단다 — 눌러 보고 빈 그림을 보는 것보다 낫다.
 */

export function AxisScaleToggle({
  name,
  log,
  disabled = false,
  onChange,
}: {
  /** 사람이 읽는 축 이름 — 「가로축」 · 「세로축」 · 「값 축」. */
  name: string
  log: boolean
  /** 로그를 쓸 수 없는 축인가(양수가 없다). */
  disabled?: boolean
  onChange: (log: boolean) => void
}) {
  return (
    <span className="inline-flex items-center gap-1" role="group" aria-label={`${name} 눈금`}>
      <span>{name}</span>
      <span className="border-border inline-flex overflow-hidden rounded border">
        {([false, true] as const).map((value) => (
          <button
            key={String(value)}
            type="button"
            aria-pressed={log === value}
            disabled={value && disabled}
            title={value && disabled ? '0 이하 값뿐이라 로그 눈금을 쓸 수 없습니다.' : undefined}
            className={`px-1.5 py-0.5 disabled:cursor-not-allowed disabled:opacity-40 ${
              log === value ? 'bg-muted text-foreground font-medium' : 'hover:bg-muted/60'
            }`}
            onClick={() => onChange(value)}
          >
            {value ? '로그' : '선형'}
          </button>
        ))}
      </span>
    </span>
  )
}
