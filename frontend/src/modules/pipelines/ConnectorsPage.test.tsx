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
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ConnectorsPage, { seenTone } from '@/modules/pipelines/ConnectorsPage'

const connectors = vi.fn()
const inbox = vi.fn()
const item = vi.fn()
const assign = vi.fn()
const discard = vi.fn()
const retry = vi.fn()
const findSpecimens = vi.fn()
const workspaces = vi.fn()

vi.mock('@/shared/components/AccessTokens', () => ({
  AccessTokens: () => <div>토큰 패널</div>,
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
})

describe('커넥터 탭', () => {
  it('마지막 보고와 대기·실패를 보여 준다', async () => {
    mount('/settings/connectors')
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
  it('시편 필요가 기본이고, 후보가 여럿이면 고르라고 한다', async () => {
    mount()
    expect(await screen.findByText('Example.tra')).toBeInTheDocument()
    expect(screen.getByText('후보 2개 — 골라 주세요')).toBeInTheDocument()
    expect(inbox).toHaveBeenCalledWith(expect.objectContaining({ status: 'needs_specimen' }))
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
