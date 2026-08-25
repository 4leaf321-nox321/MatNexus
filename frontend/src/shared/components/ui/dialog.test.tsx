/**
 * 모달은 **가운데만 굴린다.**
 *
 * 내용이 길어지면 모달이 화면 밖으로 자라고 **아래쪽 버튼을 누를 방법이
 * 사라진다.** 실사용에서 나왔다 — 기준정보에서 값을 여러 개 적으니 「추가」
 * 버튼에 닿을 수가 없었다.
 *
 * 그렇다고 바깥을 통째로 굴리면 **확인·취소가 내용과 함께 위로 사라진다.**
 * 누르려면 끝까지 굴려야 하고, 긴 모달일수록 그 거리가 멀다.
 *
 * ## 프리미티브가 지킨다
 *
 * 모달마다 적게 하면 새 모달을 만들 때마다 잊는다. 실제로 21개 중 13개가 스크롤
 * 자체를 안 갖고 있었고, **빠진 것은 내용이 길어지기 전까지 안 보인다** —
 * 만든 사람은 짧은 내용으로만 열어 보기 때문이다.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'

function open(withFooter = true) {
  render(
    <Dialog open>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>제목</DialogTitle>
        </DialogHeader>
        <p>내용</p>
        {withFooter && (
          <DialogFooter>
            <button type="button">확인</button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
  return screen.getByRole('dialog')
}

describe('모달', () => {
  it('키를 제한하고 바깥은 안 굴린다', () => {
    // 바깥이 굴러가면 바닥글이 내용과 함께 사라진다.
    const box = open()
    expect(box.className).toContain('max-h-[85vh]')
    expect(box.className).toContain('overflow-hidden')
  })

  it('가운데만 굴린다', () => {
    const box = open()
    const scroller = box.querySelector('.overflow-y-auto')
    expect(scroller).not.toBeNull()
    expect(scroller).toHaveTextContent('내용')
  })

  it('머리글과 바닥글은 굴리는 영역 밖이다', () => {
    // **버튼은 언제나 보여야 한다.** 굴리는 영역 안에 들어가면 내용이 길어질수록
    // 멀어진다.
    const box = open()
    const scroller = box.querySelector('.overflow-y-auto')
    expect(scroller).not.toBeNull()
    expect(scroller?.querySelector('[data-slot="dialog-footer"]')).toBeNull()
    expect(scroller?.querySelector('[data-slot="dialog-header"]')).toBeNull()
    // 그래도 모달 안에는 있다.
    expect(box.querySelector('[data-slot="dialog-footer"]')).not.toBeNull()
  })

  it('바닥글이 없는 모달도 그대로 돈다', () => {
    // `DialogFooter` 를 안 쓰는 모달이 둘 있다. **못 쓰게 만들지 않는다.**
    const box = open(false)
    expect(box.querySelector('.overflow-y-auto')).toHaveTextContent('내용')
  })
})
