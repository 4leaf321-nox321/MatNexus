/**
 * 휴지통 화면 — **되살릴 수 있는지 화면이 정하지 않는다.**
 *
 * 무는 자리를 고를 때 「표가 그려진다」 보다 **「못 되살리는 이유가 보인다」**·
 * 「영구 삭제가 곧장 안 나간다」 를 우선한다. 앞엣것은 시험이 없어도 눈에
 * 보이지만, 뒤엣것은 조용히 틀리고 되돌릴 수 없다.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TrashPage from '@/modules/trash/TrashPage'

const list = vi.fn()
const restore = vi.fn()
const purge = vi.fn()
const purgeMany = vi.fn()

vi.mock('@/modules/trash/api', async () => {
  const actual = await vi.importActual<typeof import('@/modules/trash/api')>(
    '@/modules/trash/api'
  )
  return {
    ...actual,
    trashApi: {
      list: (...args: unknown[]) => list(...args),
      restore: (...args: unknown[]) => restore(...args),
      purge: (...args: unknown[]) => purge(...args),
      purgeMany: (...args: unknown[]) => purgeMany(...args),
    },
  }
})

const FREE = {
  kind: 'specimen',
  kind_label: '시편',
  id: 's1',
  name: 'SECC__01_MD_01',
  deleted_at: '2026-08-28T01:00:00Z',
  workspace_id: null,
  below: {},
  blocked: null,
}

const BLOCKED = {
  kind: 'material',
  kind_label: '재료',
  id: 'm1',
  name: 'SECC_MDOI_1.0',
  deleted_at: '2026-08-28T02:00:00Z',
  workspace_id: null,
  below: { 시료: 2, 시편: 6 },
  blocked: '같은 이름의 재료가 이미 살아 있습니다: SECC_MDOI_1.0.',
}

/** 사이에 끼는 줄. **Shift 범위가 뜻을 가지려면 셋이어야 한다.** */
const MIDDLE = {
  kind: 'specimen',
  kind_label: '시편',
  id: 's2',
  name: 'SECC__01_MD_02',
  deleted_at: '2026-08-28T01:30:00Z',
  workspace_id: null,
  below: {},
  blocked: null,
}

beforeEach(() => {
  list.mockReset()
  restore.mockReset()
  purge.mockReset()
  purgeMany.mockReset()
  list.mockResolvedValue([FREE, BLOCKED])
  restore.mockResolvedValue({ name: 'x', counts: {}, said: '시편 1건' })
  purge.mockResolvedValue({ name: 'x', counts: {}, said: '시편 1건' })
  purgeMany.mockResolvedValue({ requested: 2, purged: 2, skipped: 0, counts: {}, said: '시편 2건' })
})

describe('되살리기', () => {
  it('막힌 줄은 이유를 적고 단추를 잠근다', async () => {
    /**
     * **단추만 끄면 사람은 그 자리에서 멈춘다.** 처리 화면이 「돌려 보기가 그냥
     * 비활성」 이었을 때 같은 실패를 했다 — 왜 안 되는지가 안 보였다.
     */
    render(<TrashPage />)
    await screen.findByText('SECC_MDOI_1.0')

    expect(screen.getByText(/이미 살아 있습니다/)).toBeInTheDocument()
    const buttons = screen.getAllByRole('button', { name: '되살리기' })
    // 목록 순서는 서버가 준 그대로 — 둘째 줄이 막힌 것이다.
    expect(buttons[1]).toBeDisabled()
    expect(buttons[0]).not.toBeDisabled()
  })

  it('함께 돌아오는 것을 서버가 준 대로 보인다', async () => {
    // 화면이 스스로 세면 사람이 본 숫자와 실제가 어긋난다.
    render(<TrashPage />)
    expect(await screen.findByText('시료 2건 · 시편 6건')).toBeInTheDocument()
  })

  it('누르면 그 종류와 id 로 부른다', async () => {
    render(<TrashPage />)
    await screen.findByText('SECC__01_MD_01')

    await userEvent.click(screen.getAllByRole('button', { name: '되살리기' })[0])
    await waitFor(() => expect(restore).toHaveBeenCalledWith('specimen', 's1'))
  })
})

describe('영구 삭제', () => {
  it('묻기 전에는 안 부른다', async () => {
    /** **되돌릴 수 없다.** 단추 한 번에 나가면 안 된다. */
    render(<TrashPage />)
    await screen.findByText('SECC__01_MD_01')

    await userEvent.click(screen.getAllByRole('button', { name: '영구 삭제' })[0])
    expect(purge).not.toHaveBeenCalled()
  })

  it('무엇이 사라지는지 이름과 수로 적는다', async () => {
    // 「정말 지울까요?」 만으로는 사람이 무엇에 동의하는지 모른다.
    render(<TrashPage />)
    await screen.findByText('SECC_MDOI_1.0')

    await userEvent.click(screen.getAllByRole('button', { name: '영구 삭제' })[1])
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('SECC_MDOI_1.0')
    expect(dialog).toHaveTextContent('시료 2건 · 시편 6건')
  })

  it('확인해야 나간다', async () => {
    render(<TrashPage />)
    await screen.findByText('SECC__01_MD_01')

    await userEvent.click(screen.getAllByRole('button', { name: '영구 삭제' })[0])
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: '영구 삭제', hidden: false }))

    await waitFor(() => expect(purge).toHaveBeenCalledWith('specimen', 's1'))
  })
})

describe('수집 체계', () => {
  /**
   * 시험 정의·장비 파일 정의·레시피도 소프트 삭제가 됐다. **되살리는 자리가
   * 없으면 소프트 삭제는 그냥 「안 보이는 삭제」 다** — 지운 사람은 되돌릴 길이
   * 없고, 그 행이 남아 있다는 것조차 모른다.
   */
  it('종류가 펼쳐져 있다 — 열어 봐야 아는 목록이 아니다', async () => {
    // 고를 것이 여덟이고 그중 무엇에 지운 것이 있는지가 매번 다르다. 드롭다운은
    // 고르고 나면 나머지가 무엇이었는지 사라진다.
    render(<TrashPage />)
    const picker = await screen.findByRole('group', { name: '종류로 거르기' })
    for (const name of ['전부', '재료', '시험 정의', '장비 파일 정의', '장비 커넥터']) {
      expect(within(picker).getByRole('button', { name }), name).toBeInTheDocument()
    }
  })

  it('누른 것을 다시 누르면 전부로 돌아온다', async () => {
    // **끄는 길이 있어야 토글이다.** 없으면 「전부」 를 찾아 눈이 되돌아간다.
    const user = userEvent.setup()
    render(<TrashPage />)
    const picker = await screen.findByRole('group', { name: '종류로 거르기' })
    const one = within(picker).getByRole('button', { name: '시험 정의' })
    await user.click(one)
    expect(one).toHaveAttribute('aria-pressed', 'true')
    await user.click(one)
    expect(one).toHaveAttribute('aria-pressed', 'false')
    expect(within(picker).getByRole('button', { name: '전부' })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
  })
})


describe('골라서 한꺼번에 지우기', () => {
  /**
   * **되돌릴 수 없는 자리다.** 무는 데를 고를 때 「여러 개가 지워진다」 보다
   * **「고르지 않은 것이 안 나간다」·「묻기 전에는 안 나간다」** 를 우선한다.
   */

  it('고르기 전에는 일괄 단추가 없다', async () => {
    render(<TrashPage />)
    await screen.findByText('SECC__01_MD_01')

    expect(screen.queryByRole('button', { name: '선택한 것 영구 삭제' })).toBeNull()
  })

  it('고른 것만 보낸다', async () => {
    /** **제일 위험한 자리다.** 하나를 더 보내면 그것은 돌아오지 않는다. */
    render(<TrashPage />)
    await screen.findByText('SECC__01_MD_01')

    await userEvent.click(screen.getByRole('checkbox', { name: 'SECC__01_MD_01 선택' }))
    await userEvent.click(screen.getByRole('button', { name: '선택한 것 영구 삭제' }))
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: '1건 영구 삭제' }))

    await waitFor(() =>
      expect(purgeMany).toHaveBeenCalledWith([{ kind: 'specimen', id: 's1' }])
    )
  })

  it('묻기 전에는 안 부른다', async () => {
    render(<TrashPage />)
    await screen.findByText('SECC__01_MD_01')

    await userEvent.click(screen.getByRole('checkbox', { name: 'SECC__01_MD_01 선택' }))
    await userEvent.click(screen.getByRole('button', { name: '선택한 것 영구 삭제' }))
    expect(purgeMany).not.toHaveBeenCalled()
  })

  it('Shift 로 사이에 낀 줄까지 고른다', async () => {
    /**
     * **하나씩 누르는 것이 일이 되는 자리다.** 스무 건을 지우려고 스무 번 누르면
     * 사람은 중간에 「전부 선택」 을 눌러 버리고, 그때 안 지울 것까지 딸려 간다.
     *
     * 줄이 셋이어야 이 시험이 뜻을 갖는다 — 둘뿐이면 Shift 없이 두 번 눌러도
     * 2건이라 **범위가 먹었는지 안 먹었는지 구별할 수 없다.**
     */
    list.mockResolvedValue([FREE, MIDDLE, BLOCKED])
    render(<TrashPage />)
    await screen.findByText('SECC_MDOI_1.0')

    await userEvent.click(screen.getByRole('checkbox', { name: 'SECC__01_MD_01 선택' }))
    // **`fireEvent` 다.** `userEvent.click` 의 둘째 인자는 shiftKey 를 안 받는다.
    fireEvent.click(screen.getByRole('checkbox', { name: 'SECC_MDOI_1.0 선택' }), {
      shiftKey: true,
    })

    // 가운데 줄까지 켜진다 — 두 번만 눌렀는데 3건이다.
    expect(await screen.findByText('3건')).toBeInTheDocument()
  })

  it('머리 칸으로 이 쪽 전부를 고른다', async () => {
    render(<TrashPage />)
    await screen.findByText('SECC_MDOI_1.0')

    await userEvent.click(screen.getByRole('checkbox', { name: '이 쪽 전부 선택' }))
    expect(screen.getByText('2건')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '선택한 것 영구 삭제' }))
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: '2건 영구 삭제' }))

    await waitFor(() =>
      expect(purgeMany).toHaveBeenCalledWith([
        { kind: 'specimen', id: 's1' },
        { kind: 'material', id: 'm1' },
      ])
    )
  })

  it('무엇이 사라지는지 이름으로 적는다', async () => {
    // 「2건을 지웁니다」 만으로는 어느 둘인지 모른다 — 옆줄을 눌렀을 수 있다.
    render(<TrashPage />)
    await screen.findByText('SECC_MDOI_1.0')

    await userEvent.click(screen.getByRole('checkbox', { name: '이 쪽 전부 선택' }))
    await userEvent.click(screen.getByRole('button', { name: '선택한 것 영구 삭제' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('SECC__01_MD_01')
    expect(dialog).toHaveTextContent('SECC_MDOI_1.0')
    expect(dialog).toHaveTextContent('시료 2건 · 시편 6건')
  })

  it('건너뛴 것을 말한다', async () => {
    /**
     * 겹쳐 고르면 앞선 나무에 딸려 사라진다. **다섯을 골랐는데 「셋 지움」 만
     * 뜨면 나머지가 어떻게 됐는지 사람이 모른다** — 사고가 아니라 정상이다.
     */
    purgeMany.mockResolvedValue({
      requested: 2,
      purged: 1,
      skipped: 1,
      counts: { 시료: 2 },
      said: '시료 2건',
    })
    render(<TrashPage />)
    await screen.findByText('SECC_MDOI_1.0')

    await userEvent.click(screen.getByRole('checkbox', { name: '이 쪽 전부 선택' }))
    await userEvent.click(screen.getByRole('button', { name: '선택한 것 영구 삭제' }))
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: '2건 영구 삭제' }))

    expect(await screen.findByText(/1건은 함께 사라져 건너뜀/)).toBeInTheDocument()
  })

  it('종류를 바꾸면 선택이 풀린다', async () => {
    // 걸러서 안 보이는 줄이 선택에 남아 있으면, 본 수와 지워지는 수가 어긋난다.
    render(<TrashPage />)
    await screen.findByText('SECC__01_MD_01')

    await userEvent.click(screen.getByRole('checkbox', { name: 'SECC__01_MD_01 선택' }))
    expect(screen.getByText('1건')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '재료' }))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: '선택한 것 영구 삭제' })).toBeNull()
    )
  })
})
