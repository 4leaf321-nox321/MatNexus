/**
 * 「SP」 배지 — **이어진 것만 서고, 누르면 SP 쪽을 보인다**(ADR 0063, 2026-11-02).
 *
 *   연결이 없으면 아무것도 안 그린다       목록에 빈 배지가 줄마다 서지 않는다
 *   누르면 SP 객체를 받아 보인다           이름 · key · 속성 · 관계 · 누가 언제 이었나
 *   SP 에서 사라진 것에 이어져 있으면 붉다  합쳐진 곳까지 말한다 — 낡은 연결을 다시 볼 사람이 생긴다
 *   값은 안 바뀐다고 적는다                 「이었는데 왜 이름이 그대로인가」 를 막는다
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { SpLinked, SpObjectDetail } from '@/modules/sp_core/api'
import { SpBadge } from '@/modules/sp_core/SpBadge'

const object = vi.fn()

vi.mock('@/modules/sp_core/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/sp_core/api')>()),
  spCoreApi: {
    linked: vi.fn(),
    object: (...args: unknown[]) => object(...args),
  },
}))

const LINK: SpLinked = {
  link_id: 'l1',
  target_ref: 't1',
  sp_type: 'organization',
  sp_type_label: '기관',
  sp_key: 'ORG-1',
  sp_label: '포스코',
  sp_deleted: false,
}

const DETAIL: SpObjectDetail = {
  type_slug: 'organization',
  key: 'ORG-1',
  label: '포스코',
  status: 'active',
  deleted: false,
  hidden: false,
  merged_into: null,
  previous_keys: [],
  properties: { name_en: 'POSCO', country: 'KR' },
  sp_updated_at: null,
  received_at: '2026-11-01T00:00:00Z',
  outgoing: [
    {
      src_type: 'organization',
      src: 'ORG-1',
      src_label: '포스코',
      relation: 'part_of',
      dst_type: 'organization',
      dst: 'ORG-0',
      dst_label: '포스코홀딩스',
      deleted: false,
      properties: {},
    },
  ],
  incoming: [],
  links: [
    {
      id: 'l1',
      sp_type: 'organization',
      sp_key: 'ORG-1',
      sp_label: '포스코',
      target: 'term',
      target_ref: 't1',
      target_label: 'POSCO',
      note: '이름이 같다',
      created_by: '자료관리자',
      created_at: '2026-11-01T09:30:00Z',
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  object.mockResolvedValue(DETAIL)
})

describe('SP 배지', () => {
  it('연결이 없으면 아무것도 안 그린다', () => {
    const { container } = render(<SpBadge links={undefined} label="POSCO" />)
    expect(container).toBeEmptyDOMElement()
    render(<SpBadge links={[]} label="POSCO" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('누르면 SP 객체의 이름 · key · 속성 · 관계 · 이은 사람을 보인다', async () => {
    render(<SpBadge links={[LINK]} label="POSCO" />)
    const badge = screen.getByRole('button', { name: 'POSCO — SP 연결 1개' })
    expect(badge).toHaveTextContent('SP')
    expect(object).not.toHaveBeenCalled()

    await userEvent.click(badge)
    // 받아 온 것으로 그려진 것을 기다린다 — 틀(이름 · key)은 받기 전에도 선다.
    expect(await screen.findByText('포스코홀딩스')).toBeInTheDocument()
    expect(object).toHaveBeenCalledWith('organization', 'ORG-1')
    expect(screen.getByText('기관')).toBeInTheDocument()
    expect(screen.getByText('ORG-1')).toBeInTheDocument()
    expect(screen.getByText('name_en')).toBeInTheDocument()
    expect(screen.getByText('POSCO')).toBeInTheDocument()
    expect(screen.getByText(/자료관리자 · .* 연결 — 이름이 같다/)).toBeInTheDocument()
    expect(screen.getByText(/MatNexus 의 값은 바뀌지 않습니다/)).toBeInTheDocument()
  })

  it('SP 에서 사라진 것에 이어져 있으면 붉게 서고, 합쳐진 곳을 말한다', async () => {
    object.mockResolvedValue({ ...DETAIL, deleted: true, merged_into: 'ORG-9' })
    render(
      <SpBadge
        links={[LINK, { ...LINK, link_id: 'l2', sp_key: 'ORG-2', sp_deleted: true }]}
        label="POSCO"
      />
    )
    const badge = screen.getByRole('button', {
      name: 'POSCO — SP 연결 2개 (SP 에서 사라진 것 있음)',
    })
    expect(badge).toHaveTextContent('SP 2')
    expect(badge).toHaveAttribute('data-variant', 'destructive')

    await userEvent.click(badge)
    expect(await screen.findByText(/ORG-9 에 합쳐졌습니다/)).toBeInTheDocument()
    expect(object).toHaveBeenCalledTimes(2)
  })
})
