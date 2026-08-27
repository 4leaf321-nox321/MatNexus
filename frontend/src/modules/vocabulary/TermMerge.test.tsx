/**
 * 기준정보 값 **합치기** — 이 창에서 아무 값에나 합칠 수 있는가.
 *
 * ## 왜 필요했나
 *
 * 병합은 서버에도 있었고 화면에도 있었다. 다만 **「합칠 만한 값」 패널에만**
 * 있었다 — 그건 표기가 닮은 것을 찾아 주는 장치라, `POSCO` 와 `포스코` 처럼
 * **글자가 전혀 안 닮은 같은 것**은 못 찾는다. 따로 등록된 그런 쌍은 화면에서
 * 합칠 길이 없었다.
 *
 * 지우기로도 못 푼다. 쓰는 곳이 있으면 서버가 막고(그게 맞다 — 지우면서 참조를
 * 끊으면 그 시료가 어느 제조사였는지 영영 알 수 없다), 막히면서 "감추기나
 * 병합을 쓰세요" 라고 말하는데 그 병합이 이 창에 없었다.
 *
 * ## 여기서 지키는 것
 *
 *   id 로 부른다        피커는 표기를 준다. 같은 글자가 둘이면 어느 쪽인지 모른다
 *   자기 자신은 막는다  합치는 시늉만 하고 아무 일도 안 일어난다
 *   한 번 더 묻는다     되돌릴 수 없고, 옮겨지는 것이 참조 전부다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Term } from '@/modules/vocabulary/api'
import { TermDetailDialog } from '@/modules/vocabulary/VocabularyAdminPage'

const search = vi.fn()
const merge = vi.fn()
const aliases = vi.fn()

vi.mock('@/modules/vocabulary/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/vocabulary/api')>()),
  vocabularyApi: {
    search: (...args: unknown[]) => search(...args),
    merge: (...args: unknown[]) => merge(...args),
    aliases: (...args: unknown[]) => aliases(...args),
    addAlias: vi.fn(),
    removeAlias: vi.fn(),
    update: vi.fn(),
  },
}))

/** 서버가 주는 모양 그대로. **칸을 빠뜨리면 타입 검사가 잡는다** — 실제로 잡았다. */
function term(id: string, value: string, usage = 0): Term {
  return {
    id,
    value,
    usage_count: usage,
    parent_value: null,
    attributes: {},
    extra_fields: [],
    field_count: 0,
    field_symbols: {},
    ratio_checks: [],
    status: 'active',
  }
}

const MINE = term('t1', 'POSCO', 7)
const OTHER = term('t2', '포스코', 3)

const onClose = vi.fn()

function open() {
  return render(
    <TermDetailDialog
      slug="manufacturer"
      parentSlug={null}
      term={MINE}
      onClose={onClose}
      onChanged={() => {}}
    />
  )
}

beforeEach(() => {
  search.mockReset()
  merge.mockReset()
  aliases.mockReset()
  aliases.mockResolvedValue([])
  merge.mockResolvedValue(OTHER)
  search.mockResolvedValue({ items: [MINE, OTHER], total: 2, limit: 20, offset: 0 })
  onClose.mockReset()
})

/** 합칠 대상을 고른다. 피커는 서버 검색으로 목록을 낸다. */
async function choose(user: ReturnType<typeof userEvent.setup>, value: string) {
  await user.click(await screen.findByRole('button', { name: /^다른 값에 합치기:/ }))
  await user.type(await screen.findByPlaceholderText('다른 값에 합치기 찾기'), value)
  // **행 이름은 `포스코3` 이다** — 값 뒤에 쓰는 곳 수가 붙고, jsdom 에는 그
  // 사이에 공백이 없다(스모크가 쓰는 `^값(\s|$)` 은 여기서 안 맞는다).
  await user.click(await screen.findByRole('button', { name: new RegExp(`^${value}\\d*$`) }))
}

describe('다른 값에 합치기', () => {
  it('무엇이 옮겨지고 무엇이 남는지 먼저 말한다', async () => {
    open()
    // **별칭으로 남는 것이 요점이다.** 병합이 일회성 청소가 아니라 규칙이 되는
    // 지점이고, 그걸 모르면 사람은 옛 표기가 사라진 줄 안다.
    // `/7곳/` 만으로는 창 머리의 「쓰는 곳 7곳」 까지 걸린다.
    const said = await screen.findByText(/이 값을 쓰는/)
    expect(said).toHaveTextContent('7곳')
    expect(said).toHaveTextContent('별칭으로 남습니다')
  })

  it('고르기 전에는 합치기 단추가 없다', async () => {
    open()
    await screen.findByText(/별칭으로 남습니다/)
    expect(screen.queryByRole('button', { name: '합치기' })).not.toBeInTheDocument()
  })

  it('한 번 더 물은 뒤에 부른다', async () => {
    // **되돌릴 수 없다.** 한 번에 나가면 잘못 고른 값이 그대로 참조를 가져간다.
    const user = userEvent.setup()
    open()
    await choose(user, '포스코')

    await user.click(await screen.findByRole('button', { name: '합치기' }))
    expect(merge).not.toHaveBeenCalled()

    await user.click(
      await screen.findByRole('button', { name: /'POSCO' 를 '포스코' 로 합칩니다/ })
    )
    // **id 로 부른다.** 피커는 표기를 주는데 서버는 id 를 받는다.
    await waitFor(() => expect(merge).toHaveBeenCalledWith('manufacturer', 't1', 't2'))
    expect(onClose).toHaveBeenCalled()
  })

  it('취소하면 안 부른다', async () => {
    const user = userEvent.setup()
    open()
    await choose(user, '포스코')
    await user.click(await screen.findByRole('button', { name: '합치기' }))
    await user.click(await screen.findByRole('button', { name: '취소' }))

    expect(
      screen.queryByRole('button', { name: /합칩니다/ })
    ).not.toBeInTheDocument()
    expect(merge).not.toHaveBeenCalled()
  })

  it('자기 자신은 막는다', async () => {
    // 합치는 시늉만 하고 아무 일도 안 일어나면, 사람은 합쳐진 줄 안다.
    const user = userEvent.setup()
    open()
    await choose(user, 'POSCO')

    expect(await screen.findByText(/자기 자신입니다/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '합치기' })).not.toBeInTheDocument()
  })

  it('못 찾으면 말하고 안 부른다', async () => {
    // **조용히 넘어가지 않는다.** 사이에 누가 그 값을 지웠을 수 있다.
    const user = userEvent.setup()
    open()
    await choose(user, '포스코')
    search.mockResolvedValue({ items: [MINE], total: 1, limit: 20, offset: 0 })

    await user.click(await screen.findByRole('button', { name: '합치기' }))
    await user.click(await screen.findByRole('button', { name: /합칩니다/ }))

    expect(await screen.findByText(/'포스코' 를 못 찾았습니다/)).toBeInTheDocument()
    expect(merge).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })
})
