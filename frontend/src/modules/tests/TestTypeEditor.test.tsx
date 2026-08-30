/**
 * 시험 종류 편집기 — **받은 리비전을 그대로 돌려보낸다**(ADR 0015).
 *
 * 이 정의는 한 벌 통째로 갈아 끼운다. 화면이 리비전을 안 보내면 서버가 못
 * 막고, 못 막으면 뒤에 저장한 쪽이 앞의 채널·조건을 **덮는 것이 아니라 통째로
 * 지운다.**
 *
 * 그리고 409 가 났을 때 **서버가 적어 보낸 말이 화면에 그대로 떠야 한다.**
 * "저장하지 못했습니다" 로 뭉개면 사람은 새로고침하고 자기 작업을 다시 잃는다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TestTypeEditor } from '@/modules/tests/TestTypeEditor'

const updateType = vi.fn()
const createType = vi.fn()
const capabilities = vi.fn()

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    updateType: (...args: unknown[]) => updateType(...args),
    createType: (...args: unknown[]) => createType(...args),
    parsers: () => Promise.resolve([]),
    capabilities: () => capabilities(),
  },
}))

// 편집기는 소유 부서 칸을 그리려고 로그인 정보를 읽는다. 이 시험이 보는 것은
// 리비전 왕복이라, 시스템 관리자 한 명이면 충분하다.
vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: true, memberships: [] } }),
}))

const TYPE = {
  id: 't1',
  key: 'tensile',
  label: '인장시험',
  abbr: 'TEN',
  description: null,
  parser_key: null,
  extensions: [],
  is_active: true,
  max_upload_bytes: null,
  max_upload_bytes_effective: 52428800,
  revision: 7,
  run_count: 0,
  owner_workspace_slug: null,
  owner_workspace_name: null,
  is_global: true,
  channels: [
    {
      key: 'force',
      label: '하중',
      dimension: 'force',
      si_unit: 'N',
      is_required: true,
      sort_order: 0,
    },
  ],
  conditions: [],
}

const DMA_STEP = {
  id: 'dma.derived',
  label: 'tan δ · 복소 탄성률',
  kind: 'processing',
  requires_channels: [['storage_modulus'], ['loss_modulus']],
}

beforeEach(() => {
  vi.clearAllMocks()
  capabilities.mockResolvedValue([DMA_STEP])
  updateType.mockResolvedValue(TYPE)
})

async function save() {
  await userEvent.click(await screen.findByRole('button', { name: /저장/ }))
}

describe('시험 종류 편집기', () => {
  it('열었을 때 받은 리비전을 그대로 돌려보낸다', async () => {
    render(<TestTypeEditor type={TYPE} open onSaved={vi.fn()} onClose={vi.fn()} />)
    await save()
    await waitFor(() => expect(updateType).toHaveBeenCalled())
    const [, payload] = updateType.mock.calls[0] as [string, Record<string, unknown>]
    expect(payload.expected_revision).toBe(7)
  })

  it('충돌하면 서버가 적어 보낸 말을 그대로 보인다', async () => {
    // **"저장하지 못했습니다" 로 뭉개면 안 된다.** 무엇을 해야 하는지가 그 말에
    // 들어 있다 — 누가 언제 고쳤고, 지금 저장하면 그것이 지워진다는 것.
    updateType.mockRejectedValue(
      new Error(
        '이 시험 종류가 그사이 바뀌었습니다 (열었을 때 7, 지금 9). ' +
          '홍길동 이 2026-08-24 17:30 에 고쳤습니다 — ' +
          '새로 고쳐서 다시 여세요 — 지금 저장하면 그 변경이 지워집니다.'
      )
    )
    render(<TestTypeEditor type={TYPE} open onSaved={vi.fn()} onClose={vi.fn()} />)
    await save()
    expect(await screen.findByText(/열었을 때 7, 지금 9/)).toBeInTheDocument()
    expect(screen.getByText(/지워집니다/)).toBeInTheDocument()
  })

  it('충돌하면 저장됐다고 하지 않는다', async () => {
    const onSaved = vi.fn()
    updateType.mockRejectedValue(new Error('이 시험 종류가 그사이 바뀌었습니다.'))
    render(<TestTypeEditor type={TYPE} open onSaved={onSaved} onClose={vi.fn()} />)
    await save()
    await waitFor(() => expect(updateType).toHaveBeenCalled())
    expect(onSaved).not.toHaveBeenCalled()
  })
})

describe('이 채널이면 무엇이 열리나', () => {
  it('빠진 채널을 이름으로 적는다', async () => {
    // **채널 이름은 자유인데 계산은 정해진 이름을 찾는다.** 다르게 적으면 막히는
    // 것이 아니라 목록에서 사라져서, 사람은 「이 기능이 없구나」 로 읽는다.
    render(<TestTypeEditor type={TYPE} open onClose={() => {}} onSaved={() => {}} />)
    // 배지와 이름은 형제가 아니다 — 줄 전체(배지 + 설명)를 잡는다.
    const row = (await screen.findByText(/tan δ/)).closest('div.flex') as HTMLElement
    expect(within(row).getByText('안 열림')).toBeInTheDocument()
    expect(within(row).getByText(/storage_modulus/)).toBeInTheDocument()
  })

  it('채널이 다 있으면 열린다고 말한다', async () => {
    const dma = {
      ...TYPE,
      channels: [
        { ...TYPE.channels[0], key: 'storage_modulus', label: '저장 탄성률' },
        { ...TYPE.channels[0], key: 'loss_modulus', label: '손실 탄성률' },
      ],
    }
    render(<TestTypeEditor type={dma} open onClose={() => {}} onSaved={() => {}} />)
    const row = (await screen.findByText(/tan δ/)).closest('div.flex') as HTMLElement
    expect(within(row).getByText('열림')).toBeInTheDocument()
  })

  it('목록을 화면이 적어 두지 않는다', async () => {
    // 서버가 레지스트리 선언을 그대로 준다 — 계산을 더할 때 화면도 고쳐야 하면
    // 한 곳을 빠뜨린다.
    capabilities.mockResolvedValue([
      { id: 'new.thing', label: '새 계산', kind: 'processing', requires_channels: [['torque']] },
    ])
    render(<TestTypeEditor type={TYPE} open onClose={() => {}} onSaved={() => {}} />)
    expect(await screen.findByText('새 계산')).toBeInTheDocument()
    expect(screen.getByText(/torque/)).toBeInTheDocument()
  })
})
