/**
 * 모달은 **화면을 넘으면 스크롤한다.**
 *
 * 안 그러면 내용이 길어질 때 모달이 화면 밖으로 자라고, **아래쪽 버튼을 누를
 * 방법이 사라진다.** 실사용에서 나왔다 — 기준정보에서 값을 여러 개 적으니
 * 「추가」 버튼에 닿을 수가 없었다.
 *
 * ## 프리미티브가 지킨다
 *
 * 모달마다 적게 하면 새 모달을 만들 때마다 잊는다. 실제로 21개 중 13개가 빠져
 * 있었고, **빠진 것은 내용이 길어지기 전까지 안 보인다** — 만든 사람은 짧은
 * 내용으로만 열어 보기 때문이다.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Dialog, DialogContent, DialogTitle } from '@/shared/components/ui/dialog'

function open(className?: string) {
  render(
    <Dialog open>
      <DialogContent className={className}>
        <DialogTitle>제목</DialogTitle>
        <p>내용</p>
      </DialogContent>
    </Dialog>
  )
  return screen.getByRole('dialog')
}

describe('모달', () => {
  it('기본으로 키를 제한하고 스크롤한다', () => {
    const box = open()
    expect(box.className).toContain('max-h-[85vh]')
    expect(box.className).toContain('overflow-y-auto')
  })

  it('안쪽에 자기 스크롤을 둔 모달은 덮어쓸 수 있다', () => {
    // `cn` 이 tailwind-merge 라 나중 클래스가 이긴다. 이 길이 없으면 표를
    // 안쪽에서 굴리는 모달에 스크롤바가 둘 생긴다.
    const box = open('flex flex-col overflow-hidden')
    expect(box.className).toContain('overflow-hidden')
    expect(box.className).not.toContain('overflow-y-auto')
  })
})
