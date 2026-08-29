/**
 * 장비 커넥터 화면 — **화면이 고르지 않는다.**
 *
 * 무는 자리를 「표가 그려진다」 보다 **「후보가 여럿이면 화면이 하나를 찍지 않는다」**·
 * 「이유 없이 못 버린다」 에 둔다. 앞엣것은 눈에 보이지만, 뒤엣것은 조용히 틀리고
 * 되돌릴 수 없다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ConnectorsPage, { seenTone } from '@/modules/pipelines/ConnectorsPage'

const connectors = vi.fn()
const inbox = vi.fn()
const item = vi.fn()
const assign = vi.fn()
const discard = vi.fn()
const retry = vi.fn()
const findSpecimens = vi.fn()
const workspaces = vi.fn()
const approve = vi.fn()
const approveMany = vi.fn()

vi.mock('@/shared/components/AccessTokens', () => ({
  AccessTokens: () => <div>토큰 패널</div>,
}))

/**
 * **보는 것은 모두, 손대는 것은 부서 관리자.** 목록을 모두에게 연 뒤로(서버는
 * 원래 열려 있었다) 이 화면은 두 얼굴이다 — 아래 시험 대부분은 관리자 쪽이고,
 * 마지막 묶음이 멤버에게 단추가 안 보이는 것을 확인한다.
 */
let memberships: { role: string }[] = [{ role: 'manager' }]
vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: false, memberships } }),
}))

vi.mock('@/modules/pipelines/api', async () => {
  const actual =
    await vi.importActual<typeof import('@/modules/pipelines/api')>('@/modules/pipelines/api')
  return {
    ...actual,
    pipelinesApi: {
      connectors: (...args: unknown[]) => connectors(...args),
      updateConnector: vi.fn(),
      inbox: (...args: unknown[]) => inbox(...args),
      item: (...args: unknown[]) => item(...args),
      assign: (...args: unknown[]) => assign(...args),
      discard: (...args: unknown[]) => discard(...args),
      retry: (...args: unknown[]) => retry(...args),
      findSpecimens: (...args: unknown[]) => findSpecimens(...args),
      workspaces: (...args: unknown[]) => workspaces(...args),
      approve: (...args: unknown[]) => approve(...args),
      approveMany: (...args: unknown[]) => approveMany(...args),
    },
  }
})

const CONNECTOR = {
  id: 'c1',
  name: '인장기-1',
  hostname: 'ZWICK-PC',
  workspace_id: 'w1',
  workspace_name: '금속재료팀',
  is_active: true,
  app_version: '0.1.0',
  last_seen_at: '2026-08-28T05:00:00Z',
  next_run_at: null,
  pending: 3,
  failed: 1,
  waiting: 2,
  created_by_id: 'u1',
  created_at: '2026-08-01T00:00:00Z',
}

const WAITING = {
  id: 'i1',
  status: 'needs_specimen',
  connector_id: 'c1',
  connector_name: '인장기-1',
  source_key: 'zwick',
  filename: 'Example.tra',
  size: 1234,
  sha256: 'a'.repeat(64),
  hints: { material_code: 'SECC', orientation: 'MD' },
  test_type_key: 'tensile',
  test_type_label: '인장',
  profile_key: null,
  test_run_id: null,
  test_run_name: null,
  error: null,
  candidate_count: 2,
  received_at: '2026-08-28T05:12:00Z',
  resolved_at: null,
}

const DETAIL = {
  ...WAITING,
  client_path: 'C:\\Zwick\\Example.tra',
  mtime: '2026-08-28T05:00:00Z',
  candidates: [
    {
      specimen_id: 's1',
      specimen_name: 'SECC_MDOI_1.0__01__MD_01',
      material_name: 'SECC_MDOI_1.0',
      sample_name: 'SECC_MDOI_1.0__01',
      reason: "재료 'SECC' · 방향 MD",
    },
    {
      specimen_id: 's2',
      specimen_name: 'SECC_MDOI_1.0__01__MD_02',
      material_name: 'SECC_MDOI_1.0',
      sample_name: 'SECC_MDOI_1.0__01',
      reason: "재료 'SECC' · 방향 MD",
    },
  ],
  summary: {
    channels: ['force', 'displacement'],
    row_count: 812,
    curve_count: 1,
  },
  discard_reason: null,
}

function mount(path = '/settings/connectors?tab=inbox') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ConnectorsPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  connectors.mockResolvedValue([CONNECTOR])
  inbox.mockResolvedValue({
    items: [WAITING],
    total: 1,
    limit: 100,
    offset: 0,
  })
  item.mockResolvedValue(DETAIL)
  assign.mockResolvedValue({ ...DETAIL, status: 'registered' })
  discard.mockResolvedValue(undefined)
  retry.mockResolvedValue(WAITING)
  findSpecimens.mockResolvedValue([])
  workspaces.mockResolvedValue([{ id: 'w1', slug: 'metal', name: '금속재료팀' }])
  approve.mockResolvedValue({ ...DETAIL, status: 'registered' })
  approveMany.mockResolvedValue({ approved: ['i1'], failed: {} })
})

describe('전체 탭', () => {
  it('가장 왼쪽이고 기본이다 — 상태를 안 거르고 다 보여 준다', async () => {
    mount('/settings/connectors')
    expect(await screen.findByText('Example.tra')).toBeInTheDocument()
    expect(inbox).toHaveBeenCalledWith({ limit: 100 })
  })
})

describe('커넥터 탭', () => {
  it('마지막 보고와 대기·실패를 보여 준다', async () => {
    mount('/settings/connectors?tab=connectors')
    expect(await screen.findByText('인장기-1')).toBeInTheDocument()
    expect(screen.getByText('ZWICK-PC')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('보고가 오래되면 색으로 말한다', () => {
    const now = new Date('2026-08-28T12:00:00Z').getTime()
    expect(seenTone('2026-08-28T11:30:00Z', now)).toBe('')
    expect(seenTone('2026-08-28T08:00:00Z', now)).toContain('amber')
    expect(seenTone('2026-08-26T08:00:00Z', now)).toContain('destructive')
    expect(seenTone(null, now)).toContain('muted')
  })
})

describe('수집함', () => {
  it('승인 대기가 기본 필터다 — 규칙이 맞아도 사람이 한 번 본다', async () => {
    mount()
    expect(await screen.findByText('Example.tra')).toBeInTheDocument()
    expect(inbox).toHaveBeenCalledWith(expect.objectContaining({ status: 'suggested' }))
  })

  it('승인 대기 항목은 승인 한 번으로 등록한다', async () => {
    const suggested = { ...WAITING, status: 'suggested', candidate_count: 1 }
    inbox.mockResolvedValue({ items: [suggested], total: 1, limit: 100, offset: 0 })
    item.mockResolvedValue({ ...DETAIL, status: 'suggested', candidates: [DETAIL.candidates[0]] })
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('Example.tra'))
    await user.click(await screen.findByRole('button', { name: '승인 — 시험으로 등록' }))
    await waitFor(() => expect(approve).toHaveBeenCalledWith('i1'))
  })

  it('여럿을 골라 한꺼번에 승인한다', async () => {
    const suggested = { ...WAITING, status: 'suggested', candidate_count: 1 }
    inbox.mockResolvedValue({ items: [suggested], total: 1, limit: 100, offset: 0 })
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByLabelText('Example.tra 고르기'))
    await user.click(screen.getByRole('button', { name: '고른 1건 승인' }))
    await waitFor(() => expect(approveMany).toHaveBeenCalledWith(['i1']))
  })

  it('항목을 열면 후보를 보여 주고, 고른 것만 붙인다', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('Example.tra'))
    expect(await screen.findByText('SECC_MDOI_1.0__01__MD_02')).toBeInTheDocument()

    // **화면이 먼저 찍지 않는다** — 사람이 누르기 전에는 아무것도 안 보낸다.
    expect(assign).not.toHaveBeenCalled()
    const buttons = screen.getAllByRole('button', { name: '이 시편에 붙이기' })
    expect(buttons).toHaveLength(2)
    await user.click(buttons[1])
    await waitFor(() => expect(assign).toHaveBeenCalledWith('i1', { specimen_id: 's2' }))
  })

  it('이유 없이는 못 버린다', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('Example.tra'))
    const button = await screen.findByRole('button', { name: '버리기' })
    expect(button).toBeDisabled()
    await user.type(screen.getByLabelText('버리는 이유'), '시험 실패')
    expect(button).toBeEnabled()
    await user.click(button)
    await waitFor(() => expect(discard).toHaveBeenCalledWith('i1', '시험 실패'))
  })

  it('다른 시편을 찾아 붙일 수 있다', async () => {
    findSpecimens.mockResolvedValue([
      {
        id: 's9',
        record_name: 'PA66_GF30__02__TD_01',
        material_name: 'PA66_GF30',
        sample_name: 'PA66_GF30__02',
      },
    ])
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('Example.tra'))
    await user.type(await screen.findByLabelText('시편 찾기'), 'PA66')
    await user.click(await screen.findByRole('button', { name: '붙이기' }))
    await waitFor(() => expect(assign).toHaveBeenCalledWith('i1', { specimen_id: 's9' }))
  })
})

describe('연결 정보', () => {
  it('서버 주소·부서 ID·토큰을 한 자리에 모은다', async () => {
    mount('/settings/connectors?tab=setup')
    expect(await screen.findByText('금속재료팀')).toBeInTheDocument()
    expect(screen.getByText('w1')).toBeInTheDocument()
    expect(screen.getByText('토큰 패널')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '서버 주소 복사' })).toBeInTheDocument()
  })
})

describe('실패 탭', () => {
  it('다시 읽기를 준다', async () => {
    const failed = {
      ...WAITING,
      status: 'failed',
      error: '읽을 방법이 없습니다.',
      candidate_count: 0,
    }
    inbox.mockResolvedValue({
      items: [failed],
      total: 1,
      limit: 100,
      offset: 0,
    })
    item.mockResolvedValue({ ...DETAIL, ...failed, candidates: [] })
    const user = userEvent.setup()
    mount('/settings/connectors?tab=failed')
    expect(await screen.findByText('읽을 방법이 없습니다.')).toBeInTheDocument()
    await user.click(screen.getByText('Example.tra'))
    await user.click(await screen.findByRole('button', { name: '다시 읽기' }))
    await waitFor(() => expect(retry).toHaveBeenCalledWith('i1'))
  })
})

describe('커넥터 치우기', () => {
  it('무엇이 남는지 함께 묻는다', async () => {
    // 「지웁니다」 만으로는 수집함까지 사라지는 줄 알고 못 누른다.
    const user = userEvent.setup()
    mount('/settings/connectors?tab=connectors')
    await screen.findByText('ZWICK-PC')
    await user.click(screen.getByTitle(/목록에서 치웁니다/))
    expect(await screen.findByText(/이미 들어온 파일과 그것으로 만든 시험은 그대로/)).toBeVisible()
  })

  it('멤버에게는 치우는 단추가 없다', async () => {
    memberships = [{ role: 'member' }]
    mount('/settings/connectors?tab=connectors')
    await screen.findByText('ZWICK-PC')
    expect(screen.queryByTitle(/목록에서 치웁니다/)).not.toBeInTheDocument()
    memberships = [{ role: 'manager' }]
  })
})

describe('멤버', () => {
  /**
   * **목록은 열고 손대는 것은 막는다.** 서버의 읽기 엔드포인트는 원래 열려
   * 있었는데 사이드바가 막고 있어서, 실험한 사람이 「내 파일이 왜 안 들어왔나」 를
   * 물을 데가 없었다. 열고 나면 남는 위험은 하나다 — **쓰기 단추가 그대로면
   * 누르고 403 을 본다.**
   */
  beforeEach(() => {
    memberships = [{ role: 'member' }]
  })

  afterEach(() => {
    memberships = [{ role: 'manager' }]
  })

  it('수집함은 보되 승인하지 못한다', async () => {
    mount('/settings/connectors?tab=inbox')
    expect(await screen.findByText('Example.tra')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /건 승인$/ })).not.toBeInTheDocument()
  })

  it('커넥터 상태는 보되 끄고 켜지 못한다', async () => {
    // 「내 장비가 살아 있나」 는 실험하는 사람이 먼저 묻는다.
    mount('/settings/connectors?tab=connectors')
    expect(await screen.findByText('ZWICK-PC')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '끄기' })).not.toBeInTheDocument()
  })

  it('연결 정보 탭은 아예 안 보인다 — 자격 증명이다', async () => {
    // 다른 탭과 다르다. 서버 주소·토큰·부서 id 를 모아 둔 자리라 보는 것부터 막는다.
    mount('/settings/connectors')
    await screen.findByText('Example.tra')
    expect(screen.queryByRole('tab', { name: '연결 정보' })).not.toBeInTheDocument()
  })
})

