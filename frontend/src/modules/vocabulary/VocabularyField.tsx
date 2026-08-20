/**
 * 어휘 한 칸 — **피커와 서버 검색을 한 번만 엮는다.**
 *
 * 축이 늘어날 때마다 폼에서 `search`·`onCreate` 를 베껴 쓰면 그중 하나만
 * 고쳐지는 날이 온다. 여기 한 컴포넌트를 쓰면 축 이름만 바꾸면 된다.
 */

import { vocabularyApi } from '@/modules/vocabulary/api'
import { OptionPicker } from '@/shared/components/OptionPicker'
import { Label } from '@/shared/components/ui/label'

interface Props {
  slug: string
  label: string
  value: string
  /**
   * 상위 축에서 고른 값. 주면 목록이 그 아래로 좁혀지고, 새로 만드는 값도 그
   * 아래로 들어간다.
   *
   * **부모가 없는 값은 함께 보여 준다.** 계층은 쓰면서 채워지므로 초기에는
   * 대부분 비어 있고, 감추면 아무것도 안 보인다.
   */
  parentValue?: string
  onChange: (next: string) => void
}

export function VocabularyField({ slug, label, value, parentValue, onChange }: Props) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <OptionPicker
        label={label}
        value={value}
        options={[]}
        search={async (term) => {
          const found = await vocabularyApi.search(slug, term, { parentValue })
          return found.map((item) => ({ value: item.value, count: item.usage_count }))
        }}
        onCreate={async (term) => {
          // **서버가 준 값을 고른다.** 별칭에 걸리면 친 글자와 다르다.
          const added = await vocabularyApi.create(slug, term, parentValue)
          return { value: added.value, count: added.usage_count }
        }}
        anyLabel="고르지 않음"
        onChange={onChange}
      />
    </div>
  )
}
