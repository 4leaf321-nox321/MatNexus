/**
 * 물성 카드의 내용 — **선언만으로 그린다.**
 *
 * 이 시험이 지키는 것은 하나다: **이 컴포넌트가 물성의 이름을 모른다.** 그래서
 * 여기 픽스처에는 실제 물성이 아니라 지어낸 블록이 들어 있다 — `elastic` 이나
 * `viscoelastic` 을 써서 통과하면, 이름을 아는 코드가 다시 생겨도 안 잡힌다.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CardBlocks } from '@/modules/fitting/CardBlocks'
import type { BlockSpec, PropertyCard } from '@/modules/fitting/api'

const SPECS: BlockSpec[] = [
  {
    key: 'imaginary',
    label: '지어낸 물성',
    help: '이 파일이 이름을 모른다는 것을 보이려고 지어냈다.',
    in_deck: true,
    produces: [
      { key: 'strength', label: '세기', si_unit: 'Pa', help: null },
      { key: 'ratio', label: '비', si_unit: '1', help: null },
    ],
    rows: [
      { key: 'name', label: '이름', si_unit: '1', help: null },
      { key: 'value', label: '값', si_unit: '1', help: null },
    ],
  },
  {
    key: 'sidecar',
    label: '덱에 안 가는 것',
    help: '실리는 자리가 다르다.',
    in_deck: false,
    produces: [{ key: 'note_value', label: '참고값', si_unit: '1', help: null }],
    rows: [],
  },
]

function card(blocks: Record<string, unknown>, problem: string | null = null): PropertyCard {
  return {
    id: 'card-1',
    material_id: 'm-1',
    material_name: 'M',
    test_type_key: 'tensile',
    orientation: 'MD',
    label: '카드',
    status: 'draft',
    source: {},
    blocks,
    available_formats: [],
    problem,
    point_count: 0,
    note: null,
    published_at: null,
    created_at: '2026-08-23T00:00:00Z',
  } as unknown as PropertyCard
}

describe('물성 카드 내용', () => {
  it('선언된 값만 그린다', () => {
    // **선언하지 않은 키는 payload 에 남지만 화면에는 안 뜬다** — `_source`
    // 처럼 값에 딸린 것들이 그렇다.
    render(
      <CardBlocks
        specs={SPECS}
        card={card({
          imaginary: { values: { strength: 2e8, undeclared: 999 } },
        })}
      />
    )
    expect(screen.getByText('세기')).toBeInTheDocument()
    expect(screen.queryByText('999')).not.toBeInTheDocument()
    // 값이 없는 선언은 자리를 차지하지 않는다.
    expect(screen.queryByText('비')).not.toBeInTheDocument()
  })

  it('값 옆에 출처를 보인다', () => {
    // **7850 이 실측인지 관례값인지 화면만 봐서는 모른다.**
    render(
      <CardBlocks
        specs={SPECS}
        card={card({
          imaginary: { values: { strength: 2e8, strength_source: 'material' } },
        })}
      />
    )
    expect(screen.getByText('(재료 공칭)')).toBeInTheDocument()
  })

  it('사람이 적은 값임을 짚고 근거 문서를 함께 든다', () => {
    // **시험이 준 값과 사람이 적은 값을 같은 모양으로 그리면 안 된다.**
    // 이 화면에서 그 둘이 구별되지 않으면, 문헌값으로 돌린 해석이 실측인 줄
    // 알고 나간다(ADR 0016).
    render(
      <CardBlocks
        specs={SPECS}
        card={card({
          imaginary: {
            values: {
              strength: 2e8,
              strength_source: 'declared:standard',
              strength_reference: 'KS D 3512 표 3',
            },
          },
        })}
      />
    )
    const origin = screen.getByText('(적은 값 · 규격)')
    expect(origin).toBeInTheDocument()
    // 근거 문서는 자리를 안 먹되 손에 닿는 데 둔다 — 값이 의심스러울 때
    // 확인할 길이 없으면 적어 둔 뜻이 반쯤 사라진다.
    expect(origin).toHaveAttribute('title', 'KS D 3512 표 3')
  })

  it('모르는 출처 코드는 조용히 지어내지 않는다', () => {
    // 아는 척하면 그 표시가 곧 거짓말이 된다.
    render(
      <CardBlocks
        specs={SPECS}
        card={card({
          imaginary: { values: { strength: 2e8, strength_source: 'declared:점술' } },
        })}
      />
    )
    expect(screen.getByText('(적은 값)')).toBeInTheDocument()
  })

  it('표를 접되 몇 행 접었는지 말한다', () => {
    // **조용히 자르면 그것이 전부인 줄 안다.** 소성 표 하나가 수천 점이다.
    const rows = Array.from({ length: 20 }, (_, index) => ({
      name: `p${index}`,
      value: index,
    }))
    render(<CardBlocks specs={SPECS} card={card({ imaginary: { rows } })} />)
    expect(screen.getByText('p0')).toBeInTheDocument()
    expect(screen.queryByText('p19')).not.toBeInTheDocument()
    expect(screen.getByText(/14행은 접었습니다/)).toBeInTheDocument()
  })

  it('행이 자기 단위를 들면 그것이 이긴다', () => {
    // 경화식 파라미터는 식마다 단위가 다르다 — 열 선언 하나로는 못 적는다.
    render(
      <CardBlocks
        specs={SPECS}
        card={card({ imaginary: { rows: [{ name: 'q', value: 2e8, si_unit: 'Pa' }] } })}
      />
    )
    expect(screen.getByText('200 MPa')).toBeInTheDocument()
  })

  it('덱에 안 실리는 블록을 짚는다', () => {
    // **실리지 않는다고 쓸모없는 것이 아니라 실리는 자리가 다르다.**
    render(<CardBlocks specs={SPECS} card={card({ sidecar: { values: { note_value: 1 } } })} />)
    expect(screen.getByText('덱에 안 실림')).toBeInTheDocument()
  })

  it('선언에 없는 블록은 안 그린다', () => {
    render(<CardBlocks specs={SPECS} card={card({ ogden: { values: { mu: 1 } } })} />)
    expect(screen.queryByText('ogden')).not.toBeInTheDocument()
  })

  it('못 푼 카드를 없던 일로 하지 않는다', () => {
    // 이 카드를 만든 계산이 지금 코드에 없다는 뜻이다.
    render(<CardBlocks specs={SPECS} card={card({}, '모르는 물성 블록입니다: ogden')} />)
    expect(screen.getByText(/모르는 물성 블록입니다/)).toBeInTheDocument()
  })
})
