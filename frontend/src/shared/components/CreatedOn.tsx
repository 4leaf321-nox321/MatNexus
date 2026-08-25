/**
 * 이 데이터가 **언제 생겼는가.**
 *
 * 물성에는 그 물음이 늘 따라 붙는다 — 어느 로트인가, 언제 잰 것인가, 이 카드가
 * 지난달 것인가. 아래 표 어딘가에 적어 두면 **찾아야 보이고**, 찾지 않으면
 * 모른 채로 값을 읽게 된다.
 *
 * ## 절대 시각으로 적는다
 *
 * 「3일 전」은 읽는 시점에 따라 달라진다. 화면을 캡처해 주고받는 순간 그 말은
 * 뜻을 잃고, 이 저장소의 화면은 실제로 그렇게 오간다(VOC·보고).
 *
 * ## 시각은 안 적는다
 *
 * 줄 제목 옆에 붙는 자리라 길어지면 이름이 밀린다. 날짜면 족하고, 시각까지
 * 필요한 자리는 변경 이력이다.
 */

export function CreatedOn({
  at,
  className,
  label = '등록',
}: {
  at?: string | null
  className?: string
  /** 「등록」·「만듦」처럼 그 데이터가 생긴 방식에 맞는 말. */
  label?: string
}) {
  if (!at) return null
  const when = new Date(at)
  const shown = Number.isNaN(when.getTime()) ? at : when.toLocaleDateString('ko-KR')
  return (
    <span
      className={`text-muted-foreground text-xs whitespace-nowrap ${className ?? ''}`}
      title={Number.isNaN(when.getTime()) ? undefined : when.toLocaleString('ko-KR')}
    >
      {shown} {label}
    </span>
  )
}
