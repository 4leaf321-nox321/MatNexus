/**
 * 시료 입력 필드 한 벌 — **추가와 수정이 같은 것을 쓴다.**
 *
 * 갈라져 있었다. 추가 창은 5개(로트·제조사·주 벤더·생산일·밀도), 수정 창은
 * 11개였다. 서버는 처음부터 11개를 다 받는데, **추가 창에 없는 값은 만들 때
 * 넣을 수 없어서** 만들고 나서 수정 창을 다시 열어야 했다.
 *
 * 갈라진 이유는 단순하다 — 두 곳에 같은 폼을 손으로 두 번 그렸다. 한쪽에 필드를
 * 더할 때 다른 쪽을 잊는다. `NewSampleDialog` 의 첫 주석이 정확히 이 사고를
 * 경고하고 있었는데, 그 주석이 막으려던 것은 '재료 화면 vs 시험 화면' 이었고
 * '추가 vs 수정' 은 못 봤다.
 *
 * 그래서 필드를 값으로 만든다. 여기 한 줄을 더하면 두 창에 동시에 생긴다.
 */

import { VocabularyField } from '@/modules/vocabulary/VocabularyField'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

/** 시료 폼의 상태. **문자열로 들고 있는다** — `Number('0.')` 이 0 이 되어
 *  소수점을 찍는 순간 지워진다. */
export interface SampleForm {
  lot_no: string
  alias: string
  manufacturer: string
  distributor: string
  primary_vendor: string
  sales_type: string
  production_date: string
  density: string
  note: string
}

export const EMPTY_SAMPLE: SampleForm = {
  lot_no: '',
  alias: '',
  manufacturer: '',
  distributor: '',
  primary_vendor: '',
  sales_type: '',
  production_date: '',
  density: '',
  note: '',
}

/** 폼 상태 → 서버가 받는 모양. **두 창이 같은 변환을 쓴다.** */
export function samplePayload(form: SampleForm, densityUnit: string) {
  return {
    lot_no: form.lot_no || null,
    alias: form.alias || null,
    manufacturer: form.manufacturer || null,
    distributor: form.distributor || null,
    primary_vendor: form.primary_vendor || null,
    sales_type: form.sales_type || null,
    production_date: form.production_date || null,
    density: form.density === '' ? null : Number(form.density),
    // **단위를 항상 명시해 보낸다.** 생략 가능하게 두면 "이 값이 kg/m³ 였나
    // tonne/mm³ 였나" 를 나중에 아무도 답할 수 없다.
    density_unit: densityUnit,
    note: form.note || null,
  }
}

const FIELDS: { key: keyof SampleForm; label: string; type?: string; placeholder?: string }[] = [
  { key: 'lot_no', label: '로트번호', placeholder: 'L240612' },
  { key: 'alias', label: '별칭' },
  // 제조사·유통사·주 벤더·판매유형은 여기 없다 — 기준정보 피커로 따로 그린다.
  { key: 'production_date', label: '생산일', type: 'date' },
  { key: 'density', label: '밀도 (kg/m³, 이 로트 실측)', placeholder: '7850' },
]

//: 기준정보를 거치는 칸. **유통사와 주 벤더가 같은 축을 본다** — 같은 회사가 로트에
//: 따라 둘 중 어느 쪽도 되기 때문이다.
const VOCABULARY_FIELDS: { key: keyof SampleForm; slug: string; label: string }[] = [
  { key: 'manufacturer', slug: 'manufacturer', label: '제조사' },
  { key: 'distributor', slug: 'vendor', label: '유통사' },
  { key: 'primary_vendor', slug: 'vendor', label: '주 벤더' },
  { key: 'sales_type', slug: 'sales_type', label: '판매 유형' },
]

interface Props {
  idPrefix: string
  form: SampleForm
  onChange: (key: keyof SampleForm, value: string) => void
}

export function SampleFields({ idPrefix, form, onChange }: Props) {
  return (
    <>
      {/* **제조사만 기준정보 피커다.**
          자유 텍스트로 두면 '포스코'·'포스코 '·맥에서 붙여넣은 자모 분해가 서로
          다른 제조사가 되고, 물성 탭의 "제조사가 섞였습니다" 경고가 헛돈다.
          나머지 칸은 아직 텍스트다 — 축을 하나씩 옮긴다(1단계). */}
      <div className="grid grid-cols-2 gap-3">
        {VOCABULARY_FIELDS.map(({ key, slug, label }) => (
          <VocabularyField
            key={key}
            slug={slug}
            label={label}
            value={form[key]}
            onChange={(next) => onChange(key, next)}
          />
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3">
        {FIELDS.map(({ key, label, type, placeholder }) => (
          <div key={key} className="space-y-1.5">
            <Label htmlFor={`${idPrefix}-${key}`}>{label}</Label>
            <Input
              id={`${idPrefix}-${key}`}
              type={type}
              inputMode={key === 'density' ? 'decimal' : undefined}
              placeholder={placeholder}
              value={form[key]}
              onChange={(event) => onChange(key, event.target.value)}
            />
          </div>
        ))}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-note`}>메모</Label>
        <Input
          id={`${idPrefix}-note`}
          value={form.note}
          onChange={(event) => onChange('note', event.target.value)}
        />
      </div>

      {/* **어느 자리에 무엇을 적는지가 결과를 바꾼다.** 여기 적은 밀도는 재료의
          공칭값을 이기고 카드로 들어간다. */}
      <p className="text-muted-foreground text-xs">
        전부 선택 사항입니다. 밀도는 <b>이 로트에서 잰 값</b>일 때만 넣으세요 — 카드가
        재료의 공칭값보다 이쪽을 먼저 씁니다. 푸아송비는 로트마다 달라지는 값이 아니라{' '}
        <b>재료</b>에 있습니다. 적용 제품·부위도 같은 이유로 재료에 있습니다 —
        로트마다 달라지는 값이 아닙니다.
      </p>
    </>
  )
}
