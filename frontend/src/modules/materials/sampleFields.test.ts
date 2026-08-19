/**
 * **추가 창과 수정 창이 같은 필드를 갖는가.**
 *
 * 갈라져 있었다 — 추가는 5개, 수정은 11개. 서버는 처음부터 11개를 다 받는데
 * 추가 창에 없는 값은 만들 때 넣을 수 없어, 만들고 나서 수정 창을 다시 열어야
 * 했다. 두 곳에 같은 폼을 손으로 그린 결과다.
 *
 * 이 검사는 폼이 **한 벌인지**를 본다. 어느 창이든 자기 필드 목록을 따로 들면
 * 여기서 걸린다.
 */

import { readFileSync } from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import { EMPTY_SAMPLE, samplePayload } from '@/modules/materials/SampleFields'

const read = (name: string) =>
  readFileSync(path.resolve(process.cwd(), 'src/modules/materials', name), 'utf8')

describe('시료 폼', () => {
  it('두 창이 같은 필드 목록을 쓴다', () => {
    for (const file of ['NewSampleDialog.tsx', 'EditSampleDialog.tsx']) {
      const source = read(file)
      expect(source, `${file} 이 SampleFields 를 써야 한다`).toContain('<SampleFields')
      // 자기 입력칸을 직접 그리면 그 순간 갈라진다.
      expect(source, `${file} 이 입력칸을 직접 그리면 안 된다`).not.toContain('<Input')
    }
  })

  it('서버가 받는 모든 항목을 폼이 들고 있다', () => {
    // 하나라도 빠지면 그 값은 화면에서 넣을 수 없다.
    expect(Object.keys(EMPTY_SAMPLE).sort()).toEqual(
      [
        'alias',
        'applied_part',
        'applied_product',
        'density',
        'distributor',
        'lot_no',
        'manufacturer',
        'note',
        'primary_vendor',
        'production_date',
        'sales_type',
      ].sort()
    )
  })

  it('빈 칸은 null 로, 밀도는 숫자로, 단위는 언제나 붙여 보낸다', () => {
    const payload = samplePayload({ ...EMPTY_SAMPLE, lot_no: 'L1', density: '7850' }, 'kg/m3')
    expect(payload.lot_no).toBe('L1')
    expect(payload.manufacturer).toBeNull()
    expect(payload.density).toBe(7850)
    // **단위를 생략할 수 있게 두면** 이 값이 kg/m³ 였는지 tonne/mm³ 였는지
    // 나중에 아무도 답할 수 없다.
    expect(payload.density_unit).toBe('kg/m3')
  })

  it('밀도가 비면 null 이다 — 0 이 아니다', () => {
    // 0 을 보내면 "쟀는데 0" 이 된다. 안 잰 것과 다르다.
    expect(samplePayload(EMPTY_SAMPLE, 'kg/m3').density).toBeNull()
  })
})
