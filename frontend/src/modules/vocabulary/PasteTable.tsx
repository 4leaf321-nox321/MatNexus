/**
 * 표로 붙여넣기 — **무엇을 적을 수 있는지 화면이 먼저 말한다.**
 *
 * 전에는 빈 칸에 줄을 붙여넣게 했다. 상위·값·표기 셋만 받을 때는 그래도 됐는데,
 * 속성까지 받게 되면서 **사용자가 무엇을 적어야 하는지 알 방법이 없어졌다** —
 * 헤더에 칸 이름을 적으라고만 하면 그 이름이 무엇인지 모른다. 규격의 칸은 분류가
 * 정하고 분류마다 다르다.
 *
 * 그래서 열을 **서버가 주는 목록에서 고르고**, 표에 그대로 붙여넣는다.
 *
 * ## 표는 껍데기다
 *
 * 서버로 갈 때는 지금까지와 같은 **탭으로 갈린 줄 + 헤더**가 된다. 표는 사람이
 * 보기 좋으라고 있는 것이지 새 형식이 아니다 — 형식이 둘이 되면 두 곳이 갈라진다.
 *
 * ## 숫자 열은 단위를 헤더에 적는다
 *
 * `50` 이 50 mm 인지 50 m 인지 서버가 알 방법이 없다. 화면이 표시 단위를 알고
 * 있으므로(`shared/units`) 헤더 글자를 여기서 만든다 — 사람이 적다가 틀릴 자리를
 * 없앤다.
 */

import type { ReactNode } from 'react'

import type { SpecimenField } from '@/modules/vocabulary/api'
import { PasteGrid } from '@/shared/components/PasteGrid'
import type { Column } from '@/shared/components/PasteGrid'
import { Button } from '@/shared/components/ui/button'
import { display } from '@/shared/units'

/** 숫자 칸이면 표시 단위를 괄호에 넣는다 — 서버가 그걸 보고 환산한다. */
export function headerOf(field: SpecimenField): string {
  if (field.kind !== 'number') return field.label
  const unit = display(field.si_unit, field.dimension).unit
  return unit ? `${field.label} (${unit})` : field.label
}

export function columnsOf(fields: SpecimenField[], picked: Set<string>, hasParent: boolean) {
  const fixed: Column[] = [
    ...(hasParent ? [{ key: '상위', header: '상위' }] : []),
    { key: '값', header: '값' },
    { key: '표기', header: '표기', help: '다른 표기. 여럿이면 ; 로.' },
  ]
  const chosen: Column[] = fields
    .filter((field) => picked.has(field.key))
    .map((field) => ({ key: field.key, header: headerOf(field), help: field.help }))
  return [...fixed, ...chosen]
}

export { toLines } from '@/shared/components/PasteGrid'


export function PasteTable({
  fields,
  hasParent,
  picked,
  onPicked,
  rows,
  onRows,
  borrow,
}: {
  fields: SpecimenField[]
  hasParent: boolean
  picked: Set<string>
  onPicked: (next: Set<string>) => void
  rows: string[][]
  onRows: (next: string[][]) => void
  /** 기존 값에서 열을 가져오는 자리. 축에 따라 없을 수도 있다. */
  borrow?: ReactNode
}) {
  return (
    <PasteGrid
      columns={columnsOf(fields, picked, hasParent)}
      rows={rows}
      onRows={onRows}
      required="값"
      header={
        <div className="space-y-2">
          {borrow}
          {/* **고를 수 있는 것을 먼저 보여 준다.** 이름을 알 방법이 없으면 헤더에
              무엇을 적으라는 말이 소용없다. */}
          {fields.length > 0 && (
            <div className="space-y-1">
              <p className="text-muted-foreground text-xs">
                함께 넣을 속성을 고르세요. 분류가 주는 칸과, 가져온 칸입니다.
              </p>
              <div className="flex flex-wrap gap-1">
                {fields.map((field) => (
                  <Button
                    key={field.key}
                    size="sm"
                    variant={picked.has(field.key) ? 'default' : 'outline'}
                    className="h-6 px-2 text-xs"
                    title={field.help ?? undefined}
                    onClick={() => {
                      const next = new Set(picked)
                      if (!next.delete(field.key)) next.add(field.key)
                      onPicked(next)
                    }}
                  >
                    {headerOf(field)}
                    {/* **이 칸은 새로 선언된다.** 분류가 주는 칸과 다르다 — 값을
                        넣으려면 그 규격이 그 칸을 갖게 되는 것이라, 그 사실이
                        보여야 한다. */}
                    {!field.inherited && <span className="ml-1 opacity-60">＋</span>}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </div>
      }
    />
  )
}
