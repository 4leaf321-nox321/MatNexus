/**
 * 시료·시편 탐색기 — **아코디언을 걷으면서 무엇이 사라졌나.**
 *
 * 표로 바꾸는 것은 배치 변경이지만, 그 과정에서 **편집·삭제·시편 추가가 함께
 * 사라지면 그건 개선이 아니라 기능 삭제다.** 아코디언 줄에 달려 있던 일들이라
 * 옮기다 빠뜨리기 쉽고, 화면을 열어 보기 전에는 티가 안 난다.
 *
 * 그래서 무는 자리를 「표가 뜬다」 가 아니라 셋에 둔다:
 *
 *   1. 시료를 안 눌러도 첫 시료의 시편이 보이는가 — 한 항목짜리 층을 눌러서
 *      통과하게 하지 않는 것이 표로 바꾼 이유다.
 *   2. **아코디언에 있던 일이 다 있는가** (시료 편집·밀시트·삭제 · 시편 추가·
 *      편집·삭제 · 표로 시험 넣기).
 *   3. 시료를 바꾸면 고른 시편이 풀리는가 — 안 풀면 오른쪽에 남의 시편의 시험이
 *      떠 있고, 그것이 어느 시편의 것인지 화면에 없다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SampleExplorer } from '@/modules/materials/SampleExplorer'

const specimens = vi.fn()

vi.mock('@/modules/materials/api', async () => {
  const actual = await vi.importActual<typeof import('@/modules/materials/api')>(
    '@/modules/materials/api'
  )
  return {
    ...actual,
    materialsApi: {
      ...actual.materialsApi,
      specimens: (...a: unknown[]) => specimens(...a),
    },
  }
})

vi.mock('@/modules/tests/SpecimenTests', () => ({
  SpecimenTests: ({ specimenName }: { specimenName: string }) => (
    <div>시험 목록: {specimenName}</div>
  ),
}))

const SAMPLES = [
  {
    id: 's1',
    record_name: 'SECC_1.0__01',
    lot_no: 'L24-0117',
    manufacturer: '포스코',
    specimen_count: 2,
    test_run_count: 1,
    adopted_count: 1,
    failed_count: 0,
  },
  {
    id: 's2',
    record_name: 'SECC_1.0__02',
    lot_no: 'L24-0218',
    manufacturer: '현대제철',
    specimen_count: 1,
    test_run_count: 0,
    adopted_count: 0,
    failed_count: 0,
  },
]

const specimen = (id: string, name: string, orientation: string, runs = 0) => ({
  id,
  record_name: name,
  orientation,
  standard: 'ASTM E8',
  sizes: [],
  test_run_count: runs,
  adopted_count: runs > 0 ? 1 : 0,
  failed_count: 0,
  created_at: '2026-08-01T00:00:00Z',
  registered_by: null,
})

function show() {
  render(
    <MemoryRouter>
      <SampleExplorer
        materialId="m1"
        samples={SAMPLES as never}
        onChanged={() => {}}
      />
    </MemoryRouter>
  )
}

/** jsdom 에는 `matchMedia` 가 없다. 폭을 흉내 낸다. */
function screenWidth(wide: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: wide,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  screenWidth(false)
  specimens.mockImplementation((sampleId: string) =>
    Promise.resolve(
      sampleId === 's1'
        ? [specimen('p1', 'MD_01', 'MD', 2), specimen('p2', 'TD_01', 'TD')]
        : [specimen('p3', 'DD_01', 'DD')]
    )
  )
})

describe('첫 화면', () => {
  it('시료를 안 눌러도 첫 시료의 시편이 보인다', async () => {
    // **한 항목짜리 층을 눌러서 통과하게 하지 않는다** — 아코디언에서 가장 자주
    // 하던 헛클릭이 그것이었다.
    show()
    expect(await screen.findByText('MD_01')).toBeInTheDocument()
    expect(screen.getByText('TD_01')).toBeInTheDocument()
  })

  it('시료를 가르는 것은 이름이 아니라 로트·제조사다', async () => {
    // `__01`·`__02` 만으로는 무엇이 다른지 알 수 없다.
    show()
    expect(await screen.findByText(/포스코 · L24-0117/)).toBeInTheDocument()
  })
})

describe('아코디언에 있던 일', () => {
  it('시료 편집 · 밀시트 · 삭제가 남아 있다', async () => {
    show()
    await screen.findByText('MD_01')
    expect(screen.getByRole('button', { name: /시료 편집/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /밀시트/ })).toBeInTheDocument()
  })

  it('시편 추가 · 표로 시험 넣기가 남아 있다', async () => {
    show()
    await screen.findByText('MD_01')
    expect(screen.getByRole('button', { name: /시편 추가/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /표로 시험 넣기/ })).toBeInTheDocument()
  })

  it('시편 줄마다 편집 · 삭제가 있다', async () => {
    show()
    await screen.findByText('MD_01')
    expect(screen.getAllByTitle('시편 편집')).toHaveLength(2)
    expect(screen.getAllByTitle('시편 삭제')).toHaveLength(2)
  })
})

describe('고르기', () => {
  it('시료를 바꾸면 그 시료의 시편으로 갈린다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByText('MD_01')

    await user.click(screen.getByText('SECC_1.0__02'))
    expect(await screen.findByText('DD_01')).toBeInTheDocument()
    expect(screen.queryByText('MD_01')).not.toBeInTheDocument()
  })

  it('시료를 바꾸는 순간 남의 시편의 시험이 사라진다', async () => {
    // **불러오는 동안이 문제다.** 새 시편 목록이 오기 전까지 옛 목록이 화면에
    // 남아 있고, 그때 고른 시편도 여전히 찾아진다 — 즉 **남의 시료 화면에 앞
    // 시편의 시험이 떠 있는다.** 목록이 갈리고 나면 저절로 풀리므로, 이 시험은
    // 갈리기 **전** 을 봐야 무는다(그러지 않으면 효과를 지워도 통과한다).
    let release: (value: unknown[]) => void = () => {}
    specimens.mockImplementation((sampleId: string) =>
      sampleId === 's1'
        ? Promise.resolve([specimen('p1', 'MD_01', 'MD', 2), specimen('p2', 'TD_01', 'TD')])
        : new Promise((resolve) => {
            release = resolve as (value: unknown[]) => void
          })
    )

    const user = userEvent.setup()
    show()
    await user.click(await screen.findByText('MD_01'))
    expect(await screen.findByText(/시험 목록: MD_01/)).toBeInTheDocument()

    await user.click(screen.getByText('SECC_1.0__02'))
    // 아직 새 목록이 안 왔다. 그래도 앞 시편의 시험은 이미 없어야 한다.
    expect(screen.queryByText(/시험 목록:/)).not.toBeInTheDocument()

    release([specimen('p3', 'DD_01', 'DD')])
    expect(await screen.findByText('DD_01')).toBeInTheDocument()
  })
})

describe('시험 보이는 자리', () => {
  it('넓으면 옆에서, 좁으면 줄 안에서 — 고르기 전까지는 폭이 정한다', async () => {
    // **매번 사람에게 시킬 판단이 아니다.** 넓으면 옆에 띄우는 편이 낫고(시편을
    // 바꿔 가며 견준다), 좁으면 줄 안에서 펼치는 것 말고 길이 없다.
    screenWidth(true)
    show()
    await screen.findByText('MD_01')
    expect(screen.getByRole('button', { name: /옆에서/ })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
  })

  it('고르고 나면 그 뜻이 이긴다', async () => {
    // 넓은 화면에서 일부러 「줄 안에서」 를 고른 사람에게, 창을 늘렸다고 되돌려
    // 놓으면 그건 고른 것을 무시하는 것이다.
    const user = userEvent.setup()
    screenWidth(true)
    show()
    await screen.findByText('MD_01')
    await user.click(screen.getByRole('button', { name: /줄 안에서/ }))

    expect(localStorage.getItem('mnx.sampleExplorer.mode')).toBe('inline')
    expect(screen.getByRole('button', { name: /줄 안에서/ })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
  })

  it('두 모드를 고를 수 있다 — 어느 쪽이 나은지는 써 봐야 안다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByText('MD_01')

    const side = screen.getByRole('button', { name: /옆에서/ })
    await user.click(side)
    expect(side).toHaveAttribute('aria-pressed', 'true')

    // 옆 모드에서는 고르기 전에도 그 자리가 무엇인지 말한다.
    expect(screen.getByText(/시편을 고르면 그 시험이 여기 뜹니다/)).toBeInTheDocument()

    await user.click(screen.getByText('MD_01'))
    await waitFor(() =>
      expect(screen.getByText(/시험 목록: MD_01/)).toBeInTheDocument()
    )
  })
})

describe('시험 수', () => {
  it('수만 세지 않고 채택까지 말한다', async () => {
    // 3건인데 채택이 0 이면 그 시편은 아직 물성을 못 낸 것이다.
    show()
    const row = (await screen.findByText('MD_01')).closest('tr') as HTMLElement
    expect(within(row).getByText(/시험 2/)).toBeInTheDocument()
    expect(within(row).getByText(/채택 1/)).toBeInTheDocument()
  })
})
