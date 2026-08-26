/**
 * 표 하나로 재료·시료·시편을 넣는 창.
 *
 * 묶는 규칙 자체는 `bulkRows.test.ts` 가 본다. 여기서 보는 것은 **화면이 그
 * 규칙에 무엇을 먹이는가**다 — 켠 열만 보내는지, 붙여 넣기가 보이는 열을
 * 따라가는지, 막힌 줄이 표에 남는지. 그 셋은 순수 함수만으로는 확인할 수 없다.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BulkMaterialDialog } from '@/modules/materials/BulkMaterialDialog'

const bulk = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: { bulk: (...args: unknown[]) => bulk(...args) },
}))

const NOTHING = { materials: 0, samples: 0, specimens: 0, made: [], blocked: [] }

function open() {
  return render(<BulkMaterialDialog open onClose={vi.fn()} onDone={vi.fn()} />)
}

/** `3번 줄 재료 Grade` 같은 이름으로 칸을 찾는다. */
function cell(row: number, group: string, label: string) {
  return screen.getByLabelText(`${row}번 줄 ${group} ${label}`)
}

function type(row: number, group: string, label: string, value: string) {
  fireEvent.change(cell(row, group, label), { target: { value } })
}

/** 흔한 재료 한 줄을 적는다. */
function material(row: number, grade: string) {
  type(row, '재료', 'Family', 'Metal')
  type(row, '재료', 'Category', 'Steel')
  type(row, '재료', 'Grade', grade)
}

beforeEach(() => {
  bulk.mockReset()
  bulk.mockResolvedValue(NOTHING)
})

describe('여러 개 등록', () => {
  it('열자마자 보이는 것은 재료 칸뿐이다', () => {
    open()
    expect(cell(1, '재료', 'Grade')).toBeInTheDocument()
    // 스물 몇 칸을 다 펼치면 아무것도 못 읽는다.
    expect(screen.queryByLabelText('1번 줄 시료 로트번호')).not.toBeInTheDocument()
  })

  it('열을 켜면 그 칸이 표에 생긴다', async () => {
    open()
    fireEvent.keyDown(screen.getByRole('button', { name: /열 고르기/ }), { key: 'Enter' })
    fireEvent.click(await screen.findByLabelText('시료 열 켜기'))
    await waitFor(() => expect(cell(1, '시료', '로트번호')).toBeInTheDocument())
  })

  it('꺼진 열의 값은 보내지 않는다', async () => {
    // 시료 칸을 켜서 적고 다시 끄면, 적어 둔 값이 함께 나가면 안 된다 —
    // 사람은 만들지 않기로 한 것이 만들어진 것을 나중에 안다.
    open()
    fireEvent.keyDown(screen.getByRole('button', { name: /열 고르기/ }), { key: 'Enter' })
    fireEvent.click(await screen.findByLabelText('시료 열 켜기'))
    await waitFor(() => expect(cell(1, '시료', '로트번호')).toBeInTheDocument())
    type(1, '시료', '로트번호', 'LOT-A')
    material(1, 'SECC')

    fireEvent.click(await screen.findByLabelText('시료 열 끄기'))
    await waitFor(() => expect(screen.queryByLabelText('1번 줄 시료 로트번호')).toBeNull())
    // 메뉴가 열려 있으면 나머지 화면이 `aria-hidden` 이라 눌리지 않는다.
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })

    fireEvent.click(screen.getByRole('button', { name: '등록' }))
    await waitFor(() => expect(bulk).toHaveBeenCalled())
    expect(bulk.mock.calls[0][0].materials[0].samples).toEqual([])
  })

  it('여러 개 적는 칸을 켜면 나누는 법을 말해 준다', async () => {
    // **머리글의 `(; 로 나눔)` 만으로는 안 읽힌다.** 여러 개를 적을 수 있다는
    // 것 자체를 모르면 괄호도 안 본다 — 그때 사람은 `도어, 후드` 라고 적고,
    // 그 쉼표는 붙여 넣기가 칸을 가르는 글자다.
    open()
    expect(screen.queryByText(/세미콜론/)).toBeNull()

    fireEvent.keyDown(screen.getByRole('button', { name: /열 고르기/ }), { key: 'Enter' })
    fireEvent.click(await screen.findByRole('menuitemcheckbox', { name: '적용 제품' }))
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })

    // 어느 열이 그런지도 함께 말해야 한다 — 「세미콜론으로 나누세요」 만으로는
    // 어느 칸 얘기인지 모른다.
    const notice = (await screen.findByText(/세미콜론/)).closest('p')
    expect(notice).toHaveTextContent('적용 제품')
  })

  it('클립보드가 막히면 손으로 가져갈 칸을 낸다', async () => {
    // 사내에서 개발 서버를 IP(`http://`)로 열면 브라우저가 클립보드를 안 준다.
    // **「복사하지 못했습니다」 만 띄우면 그 사람은 표를 통째로 다시 적는다** —
    // 칸이 입력란이라 끌어서 고를 수도 없다.
    document.execCommand = vi.fn(() => false)
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true })
    open()
    material(1, 'SECC')

    fireEvent.click(screen.getByRole('button', { name: /표 복사/ }))
    const box = (await screen.findByLabelText('표 글자')) as HTMLTextAreaElement
    expect(box.value).toContain('SECC')
    // 머리글도 함께 있어야 붙여 넣은 쪽에서 열을 셀 수 있다.
    expect(box.value).toContain('Grade')
  })

  it('분류를 위 줄에서 이어받는다', async () => {
    // Grade 열에만 붙여 넣는 것이 실제 작업이다. 줄마다 다시 적게 하면
    // 오타 하나가 분류를 갈라 놓는다.
    open()
    material(1, 'SECC')
    type(2, '재료', 'Grade', 'SGCC')

    fireEvent.click(screen.getByRole('button', { name: '등록' }))
    await waitFor(() => expect(bulk).toHaveBeenCalled())
    const sent = bulk.mock.calls[0][0].materials
    expect(sent).toHaveLength(2)
    expect(sent[1]).toMatchObject({ family: 'Metal', category: 'Steel', grade: 'SGCC' })
  })

  it('흠이 있으면 보내지 않는다', () => {
    // **스무 줄을 보내고 422 하나를 받으면 어느 줄인지 모른다.**
    open()
    type(1, '재료', 'Grade', 'SECC') // Family·Category 가 없다
    expect(screen.getByRole('button', { name: '등록' })).toBeDisabled()
  })

  it('막힌 줄만 표에 남는다', async () => {
    // 만들어진 줄이 남아 있으면 다시 눌렀을 때 같은 재료를 또 만들려 든다.
    bulk.mockResolvedValue({
      materials: 1,
      samples: 0,
      specimens: 0,
      made: [{ row: 0, kind: 'material', name: 'SECC', reused: false }],
      blocked: [{ row: 1, reason: '같은 이름의 재료가 이미 있습니다: SGCC' }],
    })
    open()
    material(1, 'SECC')
    material(2, 'SGCC')

    fireEvent.click(screen.getByRole('button', { name: '등록' }))
    await waitFor(() => expect(screen.getByText(/2번 줄/)).toBeInTheDocument())
    // 남은 줄은 하나뿐이고, 그것이 막혔던 줄이다.
    expect(cell(1, '재료', 'Grade')).toHaveValue('SGCC')
    expect(screen.queryByLabelText('2번 줄 재료 Grade')).toBeNull()
  })
})
