/**
 * 곡선 고르기 로직 — 화면에서 떼어 낸다.
 *
 * 상세 화면 안에 있던 것을 옮겼다. **화면 안에 있으면 시험할 수 없고, 시험할 수
 * 없으면 같은 결함이 반복된다.** 실제로 이 로직에서 두 번 났다:
 *
 *   1. 곡선을 바꿨는데 축이 그대로 → "이 시험에 없는 채널입니다: step_time"
 *   2. 축 선택지를 정의에서 뽑아 → 처리결과 곡선을 아예 그릴 수 없었다
 */

export interface CurveLike {
  key: string
  label: string | null
  kind: string
  row_count: number
  channels: string[]
}

export interface ChannelLike {
  key: string
  label: string
  si_unit: string | null
  dimension: string | null
}

export interface CurveFamily {
  name: string
  kind: string
  items: CurveLike[]
}

/**
 * 곡선을 **종류로 묶는다.** 한 파일에서 이런 것이 나온다.
 *
 *   Temperature Sweep (Multifrequency) - 2 … - 7   같은 종류, 6벌
 *   TTS - master curve (20.0 °C)                   다른 종류, 1벌
 *   TTS - shift factors                            또 다른 종류, 1벌
 *
 * 묶는 규칙은 **이름 끝의 일련번호를 떼는 것**뿐이다. 채널 구성으로 묶으면 안
 * 된다 — 실측에서 같은 종류인데도 첫 구간만 채널이 9개고 나머지는 8개였다.
 */
export function groupCurveFamilies(curves: CurveLike[]): CurveFamily[] {
  const groups = new Map<string, CurveFamily>()
  for (const curve of curves) {
    const label = curve.label ?? curve.key
    const name = familyNameOf(label)
    const found = groups.get(name)
    if (found) found.items.push(curve)
    else groups.set(name, { name, kind: curve.kind, items: [curve] })
  }
  return [...groups.values()]
}

export function familyNameOf(label: string): string {
  return label.replace(/\s*[-–#]\s*\d+\s*$/, '').trim() || label
}

/** 종류 이름을 뗀 나머지 — `- 3` 처럼 구간만 남는다. */
export function memberLabel(curve: CurveLike, familyName: string): string {
  const label = curve.label ?? curve.key
  return (
    label
      .replace(familyName, '')
      .replace(/^\s*[-–#]\s*/, '')
      .trim() || curve.key
  )
}

/**
 * 고를 수 있는 축 = **그 곡선이 실제로 가진 채널.**
 *
 * 정의(시험 종류)에서만 뽑으면 두 방향으로 틀린다.
 *
 *   - 정의에 있는데 그 곡선엔 없는 채널(DMA 는 구간마다 열 구성이 다르다)
 *   - 그 곡선엔 있는데 정의엔 없는 채널 — 마스터 곡선의 `complex_compliance` 는
 *     시험 종류에 없다. 정의 기준으로 만들면 **그 곡선을 그릴 방법이 없다**
 *
 * 곡선이 무엇을 가졌는지는 곡선이 안다. 정의는 이름과 단위를 보태 줄 뿐이다.
 */
export function axisOptionsFor(
  curve: CurveLike | null,
  declared: ChannelLike[]
): ChannelLike[] {
  const present = curve?.channels ?? declared.map((channel) => channel.key)
  return present.map((key) => {
    const found = declared.find((channel) => channel.key === key)
    return {
      key,
      label: found?.label ?? key,
      si_unit: found?.si_unit ?? null,
      dimension: found?.dimension ?? null,
    }
  })
}

/**
 * 지금 축이 그 곡선에 있나. 없으면 다시 고른다.
 *
 * 곡선을 바꿀 때마다 확인해야 한다 — 안 하면 측정 곡선의 `step_time` 을 든 채
 * 마스터 곡선으로 넘어가 오류가 뜬다(실제로 그랬다).
 */
export function resolveAxes(
  axes: { x: string; y: string } | null,
  options: ChannelLike[]
): { x: string; y: string } | null {
  if (options.length < 2) return axes
  const keys = options.map((option) => option.key)
  if (axes && keys.includes(axes.x) && keys.includes(axes.y)) return axes
  return { x: keys[0], y: keys[1] }
}
