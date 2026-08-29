/**
 * 재료 목록 옆패널.
 *
 * 실사용에서 나왔다 — 재료를 하나 고르면 상세로 들어가는데, 옆 재료를 보려면
 * **브라우저 뒤로 가기밖에 길이 없었다.**
 *
 * 여기서 지키는 것은 넷이다.
 *
 *   기본으로 열려 있다      목록을 보려고 여는 것인데 닫혀 있으면 뜻이 없다
 *   Category 는 Family 종속   `Metal + PP` 는 결과가 늘 0건이다
 *   지금 재료를 짚는다      어디 있는지 모르면 목록이 아니라 나열이다
 *   검색은 서버가 한다      앞 50개만 받아 화면에서 거르면 뒤엣것이 없는 재료가 된다
 *   잘렸으면 잘렸다고 한다   표시 없이 자르면 사람이 알 방법이 없다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MaterialListPanel } from '@/modules/materials/MaterialListPanel'
import { LeftPanelHost, LeftPanelProvider } from '@/shared/layout/SidePanel'

const list = vi.fn()
const classifications = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    list: (...args: unknown[]) => list(...args),
    classifications: () => classifications(),
  },
}))

function material(id: string, name: string, alias: string | null = null) {
  return { id, record_name: name, alias }
}

function panel(currentId?: string) {
  return render(
    <MemoryRouter>
      <LeftPanelProvider>
        {/* 껍데기가 자리를 먼저 그려야 포털이 찾는다. */}
        <LeftPanelHost />
        <MaterialListPanel currentId={currentId} />
      </LeftPanelProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useRealTimers()
  list.mockResolvedValue({
    items: [material('m1', 'DP600 1.2t'), material('m2', 'DP780 1.0t', '알루미늄판')],
    total: 2,
  })
  // 서버는 (Family, Category) 쌍으로 세어 준다.
  classifications.mockResolvedValue([
    { family: 'Metal', category: 'Steel', count: 58 },
    { family: 'Metal', category: 'Aluminum', count: 3 },
    { family: 'Polymer', category: 'PP', count: 7 },
  ])
})

describe('재료 목록 옆패널', () => {
  it('기본으로 열려 있다', async () => {
    // **목록을 보려고 여는 것이다.** 닫혀 있으면 뒤로 가기와 다를 게 없다.
    panel()
    expect(await screen.findByText('DP600 1.2t')).toBeInTheDocument()
  })

  it('지금 보고 있는 재료를 짚는다', async () => {
    panel('m2')
    const here = await screen.findByRole('link', { name: /DP780/ })
    expect(here).toHaveAttribute('aria-current', 'page')
    const other = screen.getByRole('link', { name: /DP600/ })
    expect(other).not.toHaveAttribute('aria-current')
  })

  it('누르면 그 재료로 간다', async () => {
    panel('m1')
    const link = await screen.findByRole('link', { name: /DP780/ })
    expect(link).toHaveAttribute('href', '/materials/m2')
  })

  it('검색은 서버가 한다', async () => {
    // **앞 50개를 받아 화면에서 거르면** 재료가 그보다 많아지는 순간 뒤엣것은
    // 없는 재료처럼 보인다. `MaterialPicker` 가 같은 이유로 서버 검색을 쓴다.
    panel()
    await waitFor(() => expect(list).toHaveBeenCalled())
    await userEvent.type(screen.getByLabelText('재료 찾기'), 'DP7')
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(
        expect.objectContaining({ q: 'DP7' })
      )
    )
  })

  it('잘렸으면 잘렸다고 말한다', async () => {
    list.mockResolvedValue({ items: [material('m1', 'DP600 1.2t')], total: 94 })
    panel()
    expect(await screen.findByText(/94개 중 1개/)).toBeInTheDocument()
  })

  it('전부 보이면 잘렸다고 안 한다', async () => {
    panel()
    await screen.findByText('DP600 1.2t')
    expect(screen.queryByText(/개 중 /)).not.toBeInTheDocument()
  })

  it('없으면 비었다고 말한다', async () => {
    list.mockResolvedValue({ items: [], total: 0 })
    panel()
    expect(await screen.findByText(/찾는 재료가 없습니다/)).toBeInTheDocument()
  })

  /** 팝오버를 열고 값을 고른다. 옵션은 `button` 이다(`OptionPicker`). */
  async function choose(field: RegExp, value: string) {
    await userEvent.click(screen.getByRole('button', { name: field }))
    await userEvent.click(await screen.findByText(value))
  }

  it('분류로 거르면 서버에 그 값을 준다', async () => {
    panel()
    await waitFor(() => expect(list).toHaveBeenCalled())
    await choose(/Family/, 'Metal')
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ family: 'Metal' }))
    )
  })

  it('Category 는 고른 Family 안의 것만 보인다', async () => {
    // **`Metal + PP` 는 결과가 늘 0건이다.** 고를 수 있게 두면 사람은 재료가
    // 없는 줄 안다.
    panel()
    await waitFor(() => expect(list).toHaveBeenCalled())
    await choose(/Family/, 'Metal')

    await userEvent.click(screen.getByRole('button', { name: /Category/ }))
    expect(await screen.findByText('Steel')).toBeInTheDocument()
    expect(screen.getByText('Aluminum')).toBeInTheDocument()
    expect(screen.queryByText('PP')).not.toBeInTheDocument()
  })

  it('Family 를 바꾸면 Category 를 버린다', async () => {
    // 남겨 두면 조용히 0건이 된다.
    panel()
    await waitFor(() => expect(list).toHaveBeenCalled())
    await choose(/Family/, 'Metal')
    await choose(/Category/, 'Steel')
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ category: 'Steel' }))
    )

    await choose(/Family/, 'Polymer')
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(
        expect.objectContaining({ family: 'Polymer', category: '' })
      )
    )
  })
})

describe('접기 · 펴기', () => {
  /**
   * **여닫는 손잡이는 여닫히는 것 옆에 있어야 한다.** 접는 단추가 상단 바에만
   * 있었는데, 패널에서 멀어 그것이 있는 줄도 몰랐다 — 실제로 「접기·열기 핸들을
   * 만들어 달라」 는 말이 나왔다(2026-08-30).
   *
   * 접힌 뒤에 **아무것도 안 남는 것**이 더 나쁘다. 다시 펴는 길이 화면에서
   * 사라지므로, 그 상태에 빠진 사람은 목록을 영영 못 본다.
   */
  it('접고 나면 다시 펴는 자리가 남는다', async () => {
    const user = userEvent.setup()
    panel()
    await screen.findByText('DP600 1.2t')

    await user.click(screen.getByRole('button', { name: '재료 목록 접기' }))
    expect(screen.queryByLabelText('재료 찾기')).not.toBeInTheDocument()

    // **여기가 요점이다.** 접힌 자리에 펴는 단추가 남아야 한다.
    const open = screen.getByRole('button', { name: '재료 목록 펴기' })
    await user.click(open)
    expect(await screen.findByLabelText('재료 찾기')).toBeInTheDocument()
  })
})

