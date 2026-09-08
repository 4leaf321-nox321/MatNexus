/**
 * 전체 검색 화면 — **왜 걸렸는지와 어디로 가는지.**
 *
 * 무는 것 넷:
 *   주소가 곧 검색이다            `?q=`·`?mode=` 로 들어오면 그대로 찾는다
 *   왜 걸렸는지 적는다            「비슷」 에 이유가 없으면 엉뚱한 결과로 읽힌다
 *   화면 없는 종류는 품은 것으로   시편을 누르면 그 재료가 열린다
 *   못 찾으면 다음 수를 알려 준다  「비슷으로 바꿔 보라」
 */

import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SearchPage from '@/modules/search/SearchPage'

const get = vi.fn()

vi.mock('@/shared/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client')
  return { ...actual, api: { ...actual.api, get: (...args: unknown[]) => get(...args) } }
})

function show(search: string) {
  return render(
    <MemoryRouter initialEntries={[`/search${search}`]}>
      <SearchPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  get.mockReset()
})

describe('SearchPage', () => {
  it('주소의 검색어와 방식을 그대로 쓴다', async () => {
    get.mockResolvedValue({ query: 'SECC', mode: 'similar', total: 0, groups: [] })
    show('?q=SECC&mode=similar')

    await waitFor(() => expect(get).toHaveBeenCalled())
    expect(String(get.mock.calls[0][0])).toContain('q=SECC')
    expect(String(get.mock.calls[0][0])).toContain('mode=similar')
  })

  it('왜 걸렸는지를 결과마다 적는다', async () => {
    get.mockResolvedValue({
      query: 'secc18O',
      mode: 'similar',
      total: 1,
      groups: [
        {
          kind: 'material',
          label: '재료',
          module: 'materials',
          truncated: false,
          hits: [
            {
              kind: 'material',
              id: 'm1',
              name: 'SECC180_MDOI_1.0',
              score: 0.4,
              matched: 'similar',
            },
          ],
        },
      ],
    })
    show('?q=secc18O&mode=similar')

    expect(await screen.findByText('SECC180_MDOI_1.0')).toBeInTheDocument()
    expect(screen.getByText(/비슷함/)).toBeInTheDocument()
  })

  it('시편은 품은 재료로 데려간다', async () => {
    get.mockResolvedValue({
      query: 'SECC',
      mode: 'contains',
      total: 1,
      groups: [
        {
          kind: 'specimen',
          label: '시편',
          module: 'materials',
          truncated: false,
          hits: [
            {
              kind: 'specimen',
              id: 's1',
              name: 'SECC_01__MD_02',
              score: 0.6,
              matched: 'contains',
              parent_kind: 'material',
              parent_id: 'm9',
            },
          ],
        },
      ],
    })
    show('?q=SECC')

    const link = await screen.findByRole('link', { name: 'SECC_01__MD_02' })
    expect(link).toHaveAttribute('href', '/materials/m9')
  })

  it('못 찾으면 비슷 모드를 권한다', async () => {
    get.mockResolvedValue({ query: 'zzz', mode: 'contains', total: 0, groups: [] })
    show('?q=zzz')

    expect(await screen.findByText(/찾은 것이 없습니다/)).toBeInTheDocument()
    expect(screen.getByText(/「비슷」 으로 바꾸면/)).toBeInTheDocument()
  })
})
