/**
 * 캔버스 껍데기가 지키는 것 — **넓게 보기가 실제로 화면을 덮나, 높이가 아래까지 차나.**
 *
 * 그림 자체는 여기서 안 그린다(happy-dom 에는 canvas 가 없다). 보는 것은 그 바깥의
 * 배치다 — 그리고 이 둘은 **눈으로만 확인하던 것**이라 조용히 되돌아갈 수 있었다.
 */

import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import type { CanvasNode } from '@/modules/graph/GraphCanvas'

vi.mock('@/shared/theme/ThemeProvider', () => ({
  useTheme: () => ({ theme: 'light', toggle: () => {} }),
}))
// 그림 자체는 canvas 를 쓴다 — happy-dom 에 없다. 도구 막대가 그 곁에 있으므로,
// 라이브러리 자리에 빈 것을 끼워 넣어 껍데기까지 그려지게 한다.
vi.mock('react-force-graph-2d', () => ({
  default: () => <div data-testid="force-graph" />,
}))
// happy-dom 에는 배치가 없어 모든 요소가 0×0 이다. 캔버스는 **폭이 있을 때만** 그려지고
// 도구 막대가 그 안에 있으므로, 크기를 아는 척해 줘야 단추까지 선다.
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'getBoundingClientRect', {
    value: () => ({
      width: 800,
      height: 600,
      top: 120,
      left: 0,
      right: 800,
      bottom: 720,
      x: 0,
      y: 120,
      toJSON: () => ({}),
    }),
    configurable: true,
  })
})

const NODES: CanvasNode[] = [
  { id: 'a', label: '가', color: '#2563eb', radius: 6, shape: 'circle' },
  { id: 'b', label: '나', color: '#dc2626', radius: 6, shape: 'circle' },
]

async function draw(props: Record<string, unknown> = {}) {
  const { GraphCanvas } = await import('@/modules/graph/GraphCanvas')
  const { container } = render(<GraphCanvas nodes={NODES} links={[]} {...props} />)
  return container.firstElementChild as HTMLElement
}

describe('그래프 캔버스', () => {
  it('넓게 보기는 **자리를 실제로 바꾼다**', async () => {
    // `relative` 와 `fixed` 를 함께 두면 Tailwind 가 내보내는 차례(fixed → relative)
    // 때문에 나중 것이 이긴다 — 켜도 제자리에 남고 높이만 사라져 그림이 사라졌다.
    const box = await draw()
    expect(box.className).toContain('relative')
    expect(box.className).not.toContain('fixed')

    // 그림 라이브러리는 늦게 온다(lazy) — 도구 막대가 그 뒤에 선다.
    await userEvent.click(await screen.findByRole('button', { name: '넓게 보기' }))
    expect(box.className).toContain('fixed')
    expect(box.className).not.toContain('relative')

    await userEvent.click(await screen.findByRole('button', { name: '축소' }))
    expect(box.className).toContain('relative')
  })

  it('높이를 재서 화면 아래까지 채운다', async () => {
    const box = await draw()
    // 고정값(640px)이면 큰 화면에서 아래가 빈 채로 남는다.
    expect(box.style.height).toMatch(/^\d+px$/)
    expect(Number.parseInt(box.style.height, 10)).toBeGreaterThanOrEqual(420)
  })

  it('제 높이를 가진 곳은 그것을 덮어쓸 수 있다', async () => {
    // 상세 안의 작은 관계도는 `h-[360px]!` 로 재는 높이를 이긴다.
    const box = await draw({ className: 'h-[360px]!' })
    expect(box.className).toContain('h-[360px]!')
  })
})

describe('전체화면과 관계 이름', () => {
  it('브라우저 밖까지 나가려 한다 — 막히면 안에서라도 넓어진다', async () => {
    // `fixed inset-0` 은 주소창과 탭을 못 덮는다. 그래프는 넓을수록 읽히는 그림이라
    // 그 차이가 크다.
    const request = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(HTMLElement.prototype, 'requestFullscreen', {
      value: request,
      configurable: true,
    })
    const box = await draw()
    await userEvent.click(await screen.findByRole('button', { name: '넓게 보기' }))
    expect(request).toHaveBeenCalled()
    // 브라우저가 거절해도 화면 안에서는 넓어진다 — 아무 일도 안 일어나는 것이 가장 나쁘다.
    expect(box.className).toContain('fixed')
  })

  it('관계 이름을 켜고 끈다', async () => {
    // 「저 선이 무슨 관계지」 는 그림을 보다가 나오는 물음이다. 정의 화면으로 가서
    // 확인하게 하면 그 물음은 대개 포기된다.
    await draw()
    const button = await screen.findByRole('button', { name: '관계 이름 보기' })
    expect(button).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(button)
    expect(await screen.findByRole('button', { name: '관계 이름 숨기기' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('호스트가 켜 둔 채로 시작할 수 있다 — 구조 그림이 그렇다', async () => {
    await draw({ linkLabels: true })
    expect(await screen.findByRole('button', { name: '관계 이름 숨기기' })).toBeInTheDocument()
  })
})

describe('나갈 길', () => {
  it('전체화면이 막혀도 축소가 먹는다 — 갇히지 않는다', async () => {
    // `document.fullscreenElement` 로만 판단하면, 거절당해 `fixed` 로만 넓어진 경우
    // 그 값이 비어 있어 「축소」 도 ESC 도 **다시 켜기**가 된다.
    Object.defineProperty(HTMLElement.prototype, 'requestFullscreen', {
      value: vi.fn().mockRejectedValue(new Error('거절')),
      configurable: true,
    })
    const box = await draw()
    await userEvent.click(await screen.findByRole('button', { name: '넓게 보기' }))
    expect(box.className).toContain('fixed')

    await userEvent.click(await screen.findByRole('button', { name: '축소' }))
    expect(box.className).toContain('relative')
  })
})

describe('호스트가 전체화면을 맡을 때', () => {
  it('캔버스는 자기를 안 덮는다 — 덮는 것은 호스트의 껍데기다', async () => {
    // 지식 그래프는 옆 판(고르개·상세)까지 함께 덮어야 한다. 캔버스만 덮으면 고른
    // 것의 상세를 못 읽고, 그러면 전체화면이 「크게 보기만 되는 화면」 이 된다.
    const box = await draw({ wide: true, onToggleWide: vi.fn() })
    expect(box.className).toContain('relative')
    expect(box.className).not.toContain('fixed')
  })

  it('단추는 호스트를 부른다', async () => {
    const onToggleWide = vi.fn()
    await draw({ wide: false, onToggleWide })
    await userEvent.click(await screen.findByRole('button', { name: '넓게 보기' }))
    expect(onToggleWide).toHaveBeenCalled()
  })
})

describe('빈 곳을 눌러 선택 해제', () => {
  it('가만히 클릭하면 풀린다', async () => {
    // 그림 라이브러리는 포인터가 1~2px 만 움직여도 그 누름을 「끌기」 로 보고 클릭을
    // 안 알린다 — 그 판정에만 기대면 선택 해제가 **될 때도 안 될 때도** 있다.
    const onBackgroundClick = vi.fn()
    const box = await draw({ onBackgroundClick })
    fireEvent.pointerDown(box, { clientX: 100, clientY: 100 })
    fireEvent.click(box, { clientX: 101, clientY: 101 })
    expect(onBackgroundClick).toHaveBeenCalledTimes(1)
  })

  it('끌었으면 안 풀린다 — 화면을 옮긴 것이지 고른 것이 아니다', async () => {
    const onBackgroundClick = vi.fn()
    const box = await draw({ onBackgroundClick })
    fireEvent.pointerDown(box, { clientX: 100, clientY: 100 })
    fireEvent.click(box, { clientX: 180, clientY: 140 })
    expect(onBackgroundClick).not.toHaveBeenCalled()
  })

  it('도구 막대를 눌러도 안 풀린다', async () => {
    const onBackgroundClick = vi.fn()
    await draw({ onBackgroundClick })
    await userEvent.click(await screen.findByRole('button', { name: '화면 맞춤' }))
    expect(onBackgroundClick).not.toHaveBeenCalled()
  })
})
