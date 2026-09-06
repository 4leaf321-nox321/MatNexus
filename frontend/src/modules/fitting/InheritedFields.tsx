/**
 * 푸아송비·밀도 칸 — **비우면 무엇이 들어오는지를 먼저 보인다.**
 *
 * 「재료에 있으면 비워 두세요」 로 끝내면 사람은 그 값이 무엇인지 모른 채 비운다
 * (2026-09-05). 값을 칸에 복사해 채우지는 않는다 — 두 곳에 적히면 어느 쪽이 맞는지
 * 판정할 근거가 없다. 대신 자리 표시자에 값을, 아래 줄에 출처를 적는다.
 *
 * 값은 **카드를 만드는 계산과 같은 코드**가 낸다 — 적합 응답의 `elastic`, 선언 카드
 * 미리보기의 `values`, 그 밖에는 `/fitting/cards/inherited`. 화면이 재료 API 를 읽어
 * 나름대로 판정하면 규칙이 두 벌이 되고, 어긋나는 순간 모달이 거짓말을 한다.
 */

import { useEffect, useState } from 'react'

import { fittingApi } from '@/modules/fitting/api'
import type { InheritedValue } from '@/modules/fitting/api'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { display, fromDisplay, toDisplay } from '@/shared/units'

const DENSITY_SYMBOL = display('kg/m3').unit

/** 밀도 칸의 단위는 라벨과 같다(표시 단위). 보내는 쪽은 `densityToSi` 로 되돌린다. */
export function densityToSi(typed: string): number | null {
  return typed.trim() ? fromDisplay(Number(typed), 'kg/m3') : null
}

export function InheritedFields({
  rows,
  materialId,
  idPrefix,
  poisson,
  density,
  onPoisson,
  onDensity,
}: {
  /** 이미 아는 값들(적합 응답·미리보기). 주면 서버를 안 부른다. */
  rows?: InheritedValue[]
  /** `rows` 가 없을 때 물려받을 값을 물어볼 재료. */
  materialId?: string
  idPrefix: string
  poisson: string
  density: string
  onPoisson: (next: string) => void
  onDensity: (next: string) => void
}) {
  const [fetched, setFetched] = useState<InheritedValue[] | null>(null)
  useEffect(() => {
    if (rows || !materialId) return
    let alive = true
    void fittingApi
      .inherited(materialId)
      .then((found) => alive && setFetched(found))
      // 못 읽어도 칸은 쓸 수 있어야 한다 — 그때는 예전처럼 「비우면 재료·시료에서」.
      .catch(() => alive && setFetched([]))
    return () => {
      alive = false
    }
  }, [rows, materialId])

  const known = rows ?? fetched
  const rowOf = (key: string) => known?.find((one) => one.key === key)

  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        <Field
          id={`${idPrefix}-poisson`}
          label="푸아송비"
          row={rowOf('poisson_ratio')}
          loading={known === null}
          value={poisson}
          onChange={onPoisson}
        />
        <Field
          id={`${idPrefix}-density`}
          label={`밀도 (${DENSITY_SYMBOL})`}
          siUnit="kg/m3"
          row={rowOf('density')}
          loading={known === null}
          value={density}
          onChange={onDensity}
        />
      </div>
      <p className="text-muted-foreground text-xs">
        비우면 위에 적힌 값이 그대로 들어갑니다. 여기 적으면 그 값이 이기고, 카드에
        「직접 입력」으로 남습니다 — 어느 쪽이든 카드는 <b>값과 출처를 함께</b> 박아 둡니다.
      </p>
    </>
  )
}

function Field({
  id,
  label,
  siUnit,
  row,
  loading,
  value,
  onChange,
}: {
  id: string
  label: string
  /** 있으면 서버의 SI 값을 라벨의 표시 단위로 바꿔 적는다 — 칸에 적는 값과 같은 단위여야 한다. */
  siUnit?: string
  row?: InheritedValue
  loading: boolean
  value: string
  onChange: (next: string) => void
}) {
  const known =
    row?.value != null
      ? Number((siUnit ? toDisplay(row.value, siUnit) : row.value).toPrecision(6))
      : null
  const placeholder = loading
    ? '비우면 재료·시료에서'
    : known !== null
      ? `${known} (물려받음)`
      : '값 없음 — 비우면 넣지 않음'
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        inputMode="decimal"
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      {value !== '' ? (
        <p className="text-muted-foreground text-xs">직접 입력한 값을 씁니다.</p>
      ) : !row ? null : known !== null ? (
        // **어디서 온 값인지 서버의 문장 그대로.** 화면이 다시 판정하지 않는다.
        <p className="text-muted-foreground text-xs">
          비우면 <b>{known}</b> · {row.detail ?? sourceLabel(row.source)}
        </p>
      ) : (
        <p className="text-xs text-amber-700 dark:text-amber-500">
          {row.detail ?? '물려받을 값이 없습니다.'}
        </p>
      )}
    </div>
  )
}

function sourceLabel(source: string): string {
  if (source === 'sample') return '시료에서 잰 값입니다.'
  if (source === 'material') return '재료에 적힌 값입니다.'
  return source
}
