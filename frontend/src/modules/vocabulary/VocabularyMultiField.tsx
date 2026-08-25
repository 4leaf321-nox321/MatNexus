/**
 * 기준정보를 **여러 개** 고르는 칸.
 *
 * ## 왜 필요한가
 *
 * 한 재료가 여러 제품에 들어간다. 칸 하나로 받던 동안 사람들은
 * `도어이너/후드이너` 처럼 **한 칸에 두 값을 밀어 넣었고**, 그러면 기준정보가
 * 그 덩어리를 새 용어로 만든다 — 「도어 이너」 로는 검색이 안 되고 「쓰는 곳」
 * 도 갈라진다.
 *
 * ## 고르면 비운다
 *
 * 피커 자체는 값을 안 들고 있는다. 고르는 순간 목록에 붙고 피커는 빈칸으로
 * 돌아간다 — 그래야 연달아 셋을 고를 수 있다. 고른 것은 위의 칩으로 보인다.
 *
 * ## 같은 값은 한 번만
 *
 * 목록에 같은 칩이 둘 보이면 사람은 둘 중 하나가 다른 뜻이라고 읽는다. 서버도
 * 겹친 것을 하나로 접지만, 화면에서 먼저 막아야 **눌렀는데 아무 일도 없는**
 * 것처럼 보이지 않는다.
 */

import { X } from 'lucide-react'

import { VocabularyField } from '@/modules/vocabulary/VocabularyField'
import { Badge } from '@/shared/components/ui/badge'

export function VocabularyMultiField({
  slug,
  label,
  values,
  onChange,
}: {
  slug: string
  label: string
  values: string[]
  onChange: (next: string[]) => void
}) {
  function add(picked: string) {
    const value = picked.trim()
    // 피커가 「고르지 않음」 을 돌려주면 빈 문자열이다.
    if (!value || values.includes(value)) return
    onChange([...values, value])
  }

  return (
    <div className="space-y-1.5">
      <VocabularyField slug={slug} label={label} value="" onChange={add} />
      {values.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {values.map((value) => (
            <Badge key={value} variant="secondary" className="gap-1 pr-1">
              {value}
              <button
                type="button"
                aria-label={`${value} 빼기`}
                className="hover:text-destructive"
                onClick={() => onChange(values.filter((one) => one !== value))}
              >
                <X className="size-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}
