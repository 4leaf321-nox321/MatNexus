/**
 * 기준정보 한 칸 — **피커와 서버 검색을 한 번만 엮는다.**
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
  /**
   * 목록에 없는 값을 새로 만들 수 있는가. 기본은 만들 수 있다.
   *
   * **끄는 자리가 하나 있다** — 기준정보 관리에서 상위 분류를 고를 때다. 부모는 이미
   * 있는 값이어야 하고, 강종의 부모를 손보다가 Family 를 새로 만드는 것은 아무도
   * 의도하지 않는다. 그 화면은 정리하는 자리지 늘리는 자리가 아니다.
   */
  allowCreate?: boolean
  /**
   * 도구줄용 배치 — **작은 회색 이름을 위에 두고, 옆에 붙는 이름은 지운다.**
   *
   * 기본 배치는 이름이 두 번 나온다(위의 `Label` 과 피커가 트리거 옆에 다는
   * 것). 세로 폼에서는 눈에 안 띄지만, 칸이 가로로 늘어선 도구줄에서는 옆
   * 칸들과 이름 크기도 높이도 안 맞아 어디까지가 한 칸인지 안 보인다.
   */
  compact?: boolean
  onChange: (next: string) => void
}

export function VocabularyField({
  slug,
  label,
  value,
  parentValue,
  allowCreate = true,
  compact = false,
  onChange,
}: Props) {
  return (
    <div className={compact ? 'space-y-1' : 'space-y-1.5'}>
      <Label className={compact ? 'text-muted-foreground text-xs' : undefined}>{label}</Label>
      <OptionPicker
        label={label}
        showLabel={!compact}
        triggerClassName={compact ? 'h-9 w-full justify-between' : ''}
        value={value}
        options={[]}
        search={async (term) => {
          const found = await vocabularyApi.search(slug, term, { parentValue })
          return found.items.map((item) => ({ value: item.value, count: item.usage_count }))
        }}
        onCreate={
          allowCreate
            ? async (term) => {
                // **서버가 준 값을 고른다.** 별칭에 걸리면 친 글자와 다르다.
                const added = await vocabularyApi.create(slug, term, parentValue)
                return { value: added.value, count: added.usage_count }
              }
            : undefined
        }
        anyLabel="고르지 않음"
        onChange={onChange}
      />
    </div>
  )
}
