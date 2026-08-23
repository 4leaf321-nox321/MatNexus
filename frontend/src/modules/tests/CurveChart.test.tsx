/**
 * 로그 축 — **마스터커브는 이것 없이 못 읽는다.**
 *
 * 환산 주파수는 일곱 자릿수에 걸치고 저장 탄성률도 세 자릿수다. 선형으로 그리면
 * 점 대부분이 왼쪽 끝 한 칸에 뭉쳐 곡선의 모양이 사라진다.
 *
 * 그림을 눈으로 볼 수 없으니 **좌표를 읽어서** 확인한다. 자리를 log 로 잡았는지,
 * 그리고 눈금 라벨은 원래 값으로 되돌렸는지(사람은 Hz 로 읽지 log Hz 로 읽지
 * 않는다) 둘 다 본다.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CurveChart } from '@/modules/tests/CurveChart'

/** 세 자릿수씩 벌어진 세 점. 가운데가 로그 축에서는 정확히 한가운데다. */
const DECADES: [number, number][] = [
  [1e-3, 1e6],
  [1, 1e8],
  [1e3, 1e9],
]

function xCoordinates(container: HTMLElement): number[] {
  const path = container.querySelector('path')
  const drawn = path?.getAttribute('d') ?? ''
  return drawn.split(/[ML]/).filter(Boolean).map((pair) => Number(pair.split(',')[0]))
}

describe('CurveChart 로그 축', () => {
  it('로그 축에서는 한 자릿수가 한 칸이다', () => {
    const { container } = render(
      <CurveChart points={DECADES} xLabel="주파수" yLabel="탄성률" logX logY />
    )

    const [left, middle, right] = xCoordinates(container)
    // 1e-3 · 1 · 1e3 은 로그 자리로 -3 · 0 · 3 이라 가운데가 정확히 한가운데다.
    expect(middle).toBeCloseTo((left + right) / 2, 6)
  })

  it('기본은 선형이다 — 기존 곡선의 자리가 바뀌면 안 된다', () => {
    const { container } = render(
      <CurveChart points={DECADES} xLabel="변형률" yLabel="응력" />
    )

    const [left, middle, right] = xCoordinates(container)
    // 1 은 1000 에 견주면 거의 0 이라 왼쪽 끝에 붙는다.
    expect(middle - left).toBeLessThan((right - left) * 0.01)
  })

  it('눈금 라벨은 원래 값으로 적는다', () => {
    render(<CurveChart points={DECADES} xLabel="주파수" yLabel="탄성률" logX logY />)

    expect(screen.getByText('1')).toBeTruthy() // 1 Hz
    expect(screen.getByText('100')).toBeTruthy() // 100 Hz
    expect(screen.getByText('1.00e+9')).toBeTruthy() // 1 GPa
    // 로그 값이 그대로 새면 여기에 '9' 나 '-3' 이 뜬다.
    expect(screen.queryByText('9')).toBeNull()
    expect(screen.queryByText('-3')).toBeNull()
  })

  it('로그 y 축은 0 을 바닥에 깔지 않는다', () => {
    // 선형 축은 응력·하중을 0 부터 보여 주는 것이 실무 감각이지만, 0 은 로그
    // 축에 자리가 없다. 깔면 세 자릿수짜리 곡선이 한 줄로 뭉친다.
    render(<CurveChart points={DECADES} xLabel="주파수" yLabel="탄성률" logX logY />)

    expect(screen.queryByText('0')).toBeNull()
    expect(screen.getByText('1.00e+6')).toBeTruthy() // 가장 작은 값이 바닥이다
  })
})

/**
 * 경계선 — **외삽을 그릴 때 없으면 안 된다.**
 *
 * 늘린 구간과 측정 구간은 선 하나로 이어져 있다. 경계를 표시하지 않으면 어디까지가
 * 시험이고 어디부터가 식의 주장인지 구별할 방법이 없고, 그 구별이 없으면 지어낸
 * 값을 측정값으로 읽는다.
 */
describe('CurveChart 경계선', () => {
  const POINTS: [number, number][] = [
    [0, 300],
    [0.1, 450],
    [0.2, 500],
  ]

  it('준 자리에 선을 긋고 이름을 적는다', () => {
    const { container } = render(
      <CurveChart
        points={POINTS}
        xLabel="진소성변형률"
        yLabel="진응력"
        marker={{ x: 0.2, label: '여기까지 시험' }}
      />,
    )
    expect(screen.getByText('여기까지 시험')).toBeInTheDocument()
    // 점선이어야 눈금선과 구별된다.
    const dashed = container.querySelectorAll('line[stroke-dasharray]')
    expect(dashed).toHaveLength(1)
    // 곡선의 마지막 x 와 같은 자리에 서야 한다.
    const last = Number(
      (container.querySelector('path')?.getAttribute('d') ?? '')
        .split(/[ML]/)
        .filter(Boolean)
        .at(-1)
        ?.split(',')[0],
    )
    expect(Number(dashed[0].getAttribute('x1'))).toBeCloseTo(last, 3)
  })

  it('안 주면 긋지 않는다', () => {
    // 안 늘렸으면 경계가 곧 곡선 끝이라 선이 겹친다.
    const { container } = render(
      <CurveChart points={POINTS} xLabel="진소성변형률" yLabel="진응력" />,
    )
    expect(container.querySelectorAll('line[stroke-dasharray]')).toHaveLength(0)
  })
})
