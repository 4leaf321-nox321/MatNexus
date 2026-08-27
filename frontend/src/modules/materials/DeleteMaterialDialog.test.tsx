/**
 * 재료 사슬 삭제 — **묻지 않고 지우지 않는가.**
 *
 * 여기서 틀리면 사라지는 것이 한 줄이 아니라 트리 전체다. 그리고 사람이 「예」 를
 * 누른 근거는 이 화면이 보여 준 숫자이므로, 숫자와 실제가 어긋나면 그 「예」 는
 * 다른 것에 대한 대답이 된다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DeleteMaterialDialog } from '@/modules/materials/DeleteMaterialDialog'

const deletePlan = vi.fn()
const removeCascade = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    deletePlan: (...args: unknown[]) => deletePlan(...args),
    removeCascade: (...args: unknown[]) => removeCascade(...args),
  },
}))

const onDeleted = vi.fn()

function open() {
  return render(
    <DeleteMaterialDialog
      materialId="m1"
      materialName="SPCC_-_1.2"
      open
      onClose={() => {}}
      onDeleted={onDeleted}
    />
  )
}

function plan(samples: number, specimens: number, test_runs: number) {
  return { material_name: 'SPCC_-_1.2', samples, specimens, test_runs }
}

beforeEach(() => {
  deletePlan.mockReset()
  removeCascade.mockReset()
  removeCascade.mockResolvedValue({})
  onDeleted.mockReset()
})

describe('무엇이 사라지는지', () => {
  it('서버가 센 것을 그대로 보여 준다', async () => {
    deletePlan.mockResolvedValue(plan(2, 6, 0))
    open()
    // **줄 단위로 본다.** `/시료/` 는 순서를 설명하는 문장에도 걸린다.
    const rows = await screen.findAllByRole('listitem')
    expect(rows.map((one) => one.textContent)).toEqual(['시료 2건', '시편 6건'])
  })

  it('아무것도 안 달렸으면 그렇게 말한다', async () => {
    deletePlan.mockResolvedValue(plan(0, 0, 0))
    open()
    expect(await screen.findByText(/아무것도 딸려 있지 않습니다/)).toBeInTheDocument()
  })

  it('열 때 다시 센다', async () => {
    // **사이에 누가 시편을 넣었을 수 있다.** 사람은 지금 화면의 숫자를 보고
    // 누르므로, 그 숫자가 열 때의 것이어야 한다.
    deletePlan.mockResolvedValue(plan(1, 1, 0))
    open()
    await waitFor(() => expect(deletePlan).toHaveBeenCalledWith('m1'))
  })
})

describe('시험이 달려 있으면', () => {
  it('칸을 켜기 전에는 못 지운다', async () => {
    // **시료·시편은 이름표에 가깝지만 시험은 잰 값이다.** 한 칸으로 묶으면
    // 「시료 정리하려다 측정 데이터를 날렸다」 가 난다.
    deletePlan.mockResolvedValue(plan(1, 3, 3))
    open()
    expect(await screen.findByText(/곡선과 처리 결과가 여기 매달려/)).toBeInTheDocument()

    const button = screen.getByRole('button', { name: '지우기' })
    expect(button).toBeDisabled()

    await userEvent.click(screen.getByRole('checkbox'))
    expect(button).toBeEnabled()
  })

  it('켜고 지우면 그 뜻이 서버에 간다', async () => {
    deletePlan.mockResolvedValue(plan(1, 3, 3))
    open()
    await screen.findByRole('checkbox')
    await userEvent.click(screen.getByRole('checkbox'))
    await userEvent.click(screen.getByRole('button', { name: '지우기' }))

    await waitFor(() => expect(removeCascade).toHaveBeenCalledWith('m1', true))
    expect(onDeleted).toHaveBeenCalled()
  })

  it('시험이 없으면 칸이 아예 없다', async () => {
    // 있으나 마나 한 칸을 늘 띄우면 사람이 습관적으로 켜게 되고, 그러면 칸이
    // 막는 일을 못 한다.
    deletePlan.mockResolvedValue(plan(1, 3, 0))
    open()
    await screen.findByText(/함께 사라집니다/)
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '지우기' })).toBeEnabled()
  })

  it('시험이 없으면 안 지운다고 보낸다', async () => {
    deletePlan.mockResolvedValue(plan(1, 3, 0))
    open()
    await screen.findByText(/함께 사라집니다/)
    await userEvent.click(screen.getByRole('button', { name: '지우기' }))
    await waitFor(() => expect(removeCascade).toHaveBeenCalledWith('m1', false))
  })
})

describe('실패하면', () => {
  it('이유를 보여 주고 닫지 않는다', async () => {
    // **조용히 닫히면 지워진 줄 안다.** 그리고 목록으로 옮겨 가서 없는 것을
    // 찾게 된다.
    deletePlan.mockResolvedValue(plan(1, 1, 0))
    removeCascade.mockRejectedValue(new Error('권한이 없습니다'))
    open()
    await screen.findByText(/함께 사라집니다/)
    await userEvent.click(screen.getByRole('button', { name: '지우기' }))

    expect(await screen.findByText(/권한이 없습니다/)).toBeInTheDocument()
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('세지 못해도 화면이 멈추지 않는다', async () => {
    deletePlan.mockRejectedValue(new Error('세지 못했습니다'))
    open()
    expect(await screen.findByText(/세지 못했습니다/)).toBeInTheDocument()
    // 셀 수 없으면 지울 수도 없다 — 무엇이 사라지는지 모르는 채로 누르게 된다.
    expect(screen.getByRole('button', { name: '지우기' })).toBeDisabled()
  })
})
