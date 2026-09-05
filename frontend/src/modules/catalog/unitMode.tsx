/**
 * 카탈로그 단위 모드 — **표시용(실무)과 SI 사이를 고른다.**
 *
 * 기본은 표시용이다 — 시스템의 나머지 화면(시험·처리)이 그렇게 보여 준다
 * (`shared/units.ts`, v1.88.0). SI 는 문헌 원문과 대조할 때 쓴다. 선택은 이
 * 브라우저가 기억한다 — 보는 방식이지 데이터가 아니라서 새어도 잃을 것이 없다.
 */

import { useState } from 'react'

import type { UnitMode } from '@/modules/catalog/api'

const STORAGE_KEY = 'matnexus.catalog.units'

function stored(): UnitMode {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'si' ? 'si' : 'display'
  } catch {
    return 'display'
  }
}

export function useUnitMode(): [UnitMode, (next: UnitMode) => void] {
  const [mode, setMode] = useState<UnitMode>(stored)
  return [
    mode,
    (next) => {
      setMode(next)
      try {
        localStorage.setItem(STORAGE_KEY, next)
      } catch {
        // 저장 못 해도 이번 화면에서는 동작한다.
      }
    },
  ]
}

export function UnitModeToggle({
  mode,
  onChange,
}: {
  mode: UnitMode
  onChange: (next: UnitMode) => void
}) {
  return (
    <label className="flex items-center gap-1.5 text-sm">
      <span className="text-muted-foreground text-xs">단위</span>
      <select
        aria-label="단위 모드"
        className="border-input bg-background h-8 rounded-md border px-2 text-sm"
        value={mode}
        onChange={(event) => onChange(event.target.value as UnitMode)}
      >
        <option value="display">표시용 (MPa · °C …)</option>
        <option value="si">SI (Pa · K …)</option>
      </select>
    </label>
  )
}
