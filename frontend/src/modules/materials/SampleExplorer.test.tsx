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
        onAddSample={() => {}}
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
    // **줄마다 붙는다.** 이름에 그 시료가 들어가야 무엇을 고치는지 화면이 말한다.
    expect(
      screen.getByRole('button', { name: 'SECC_1.0__01 편집' })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'SECC_1.0__01 삭제' })
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /밀시트/ })).toBeInTheDocument()
  })

  it('줄마다 제 것이 붙는다 — 시료가 둘이면 단추도 두 벌', async () => {
    // 머리에 하나만 두면 목록이 길 때 무엇에 거는지 안 보인다.
    show()
    await screen.findByText('MD_01')
    expect(screen.getByRole('button', { name: 'SECC_1.0__02 편집' })).toBeInTheDocument()
  })

  it('편집을 누르면 그 줄이 고른 것이 된다', async () => {
    // **누른 줄이 곧 대상이다.** 안 그러면 창에 뜬 이름과 목록에서 강조된 줄이
    // 어긋나고, 그때 사람은 남의 시료를 고치고 있다.
    const user = userEvent.setup()
    show()
    await screen.findByText('MD_01')
    await user.click(screen.getByRole('button', { name: 'SECC_1.0__02 편집' }))
    expect(await screen.findByText('DD_01')).toBeInTheDocument()
  })

  it('시편 추가가 남아 있다', async () => {
    show()
    await screen.findByText('MD_01')
    expect(screen.getByRole('button', { name: /시편 추가/ })).toBeInTheDocument()
  })

  it('표로 시험 넣기가 남아 있다 — 시험 쪽에서', async () => {
    // **곡선 없는 시험도 데이터다.** 기존 표에 쌓인 것을 못 가져오면 사용자가
    // 옮겨오지 않는다. 자리만 시험 열로 옮겼지 없앤 것이 아니다.
    screenWidth(true)
    show()
    await screen.findByText('MD_01')
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

  it('열기만 한 것은 고른 것이 아니다 — 옛 값에 안 끌린다', async () => {
    // 앞 판은 마운트에서 지금 모드를 적었다. 그 값이 사람의 뜻 행세를 하면
    // **창을 늘려도 모드가 안 바뀐다** — 실제로 그렇게 났다(2026-08-30).
    localStorage.setItem('mnx.sampleExplorer.mode', 'inline')
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

    expect(localStorage.getItem('mnx.sampleExplorer.mode.choice')).toBe('inline')
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

describe('일이 붙는 자리', () => {
  /**
   * **일은 그 대상이 있는 열에서 한다** (2026-08-30).
   *
   * 전에는 시료 편집·밀시트·삭제와 시편 추가가 **모두 가운데(시편) 열 머리**에
   * 몰려 있었고, 시료 추가는 아예 화면 맨 위에 있었다. 그러면 「이 편집이 시료를
   * 고치는 건지 시편을 고치는 건지」 가 자리로 안 드러나, 누를 때마다 글자를
   * 읽어 확인하게 된다.
   *
   * 자리가 층을 말하게 한다: 시료의 일은 시료 목록 열에, 시편의 일은 시편 표 열에.
   */
  const columnOf = (name: string | RegExp) => {
    const button = screen.getByRole('button', { name })
    // 열은 그리드의 직계 자식이다.
    return button.closest('.space-y-1, .min-w-0')
  }

  it('시료의 일은 시료 목록 열에 있다', async () => {
    show()
    await screen.findByText('MD_01')
    const list = columnOf(/시료 추가/)
    expect(list).not.toBeNull()
    // 편집·밀시트·삭제가 같은 열에 있어야 한다 — 셋 다 시료에 거는 일이다.
    expect(columnOf('SECC_1.0__01 편집')).toBe(list)
    expect(columnOf(/밀시트/)).toBe(list)
    expect(columnOf('SECC_1.0__01 삭제')).toBe(list)
  })

  it('시편의 일은 시편 표 열에 있다', async () => {
    show()
    await screen.findByText('MD_01')
    const table = columnOf(/시편 추가/)
    expect(table).not.toBeNull()
    // **두 열이 서로 다른 자리다.** 같으면 옮긴 뜻이 없다.
    expect(table).not.toBe(columnOf(/시료 추가/))
  })

  it('시험을 넣는 일은 시험 쪽에 있다', async () => {
    // **시편을 더하는 일과 시험을 더하는 일은 다른 층이다.** 나란히 두면 한
    // 묶음처럼 보이고, 그러면 「시편을 넣는 김에 시험도」 로 읽힌다.
    screenWidth(true)
    show()
    await screen.findByText('MD_01')
    const bulk = screen.getByRole('button', { name: /표로 시험 넣기/ })
    const add = screen.getByRole('button', { name: /시편 추가/ })
    expect(bulk.closest('.min-w-0')).not.toBe(add.closest('.min-w-0'))
  })

  it('밀시트는 고른 시료의 것이다', async () => {
    // 줄마다 붙일 일이 아니다 — 한 시료에 밀시트는 하나이고, 그것을 보는 것은
    // 고르고 나서 하는 일이다.
    show()
    await screen.findByText('MD_01')
    expect(screen.getAllByRole('button', { name: /밀시트/ })).toHaveLength(1)
  })
})

describe('보기 모드에 따라', () => {
  it('줄 안에서 모드에도 표로 시험 넣기가 있다', async () => {
    // **모드를 바꿨다고 기능이 없어지면 안 된다.** 그 모드에는 시험 열이 없으므로
    // 시편 열 머리에 둔다 — 자리는 옮기되 길은 남긴다.
    screenWidth(false)
    show()
    await screen.findByText('MD_01')
    expect(screen.getByRole('button', { name: /표로 시험 넣기/ })).toBeInTheDocument()
  })

  it('두 모드에서 한 번씩만 나온다', async () => {
    // 둘 다 그리면 같은 일이 두 자리에 있고, 그때 어느 쪽이 진짜인지 모른다.
    screenWidth(true)
    show()
    await screen.findByText('MD_01')
    expect(screen.getAllByRole('button', { name: /표로 시험 넣기/ })).toHaveLength(1)
  })
})
