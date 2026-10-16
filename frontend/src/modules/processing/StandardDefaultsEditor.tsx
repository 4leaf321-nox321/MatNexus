/**
 * 시편 규격의 **처리 기본값** — 처리 단계 → 옵션 → 값(2026-10-16).
 *
 * 처리 단계는 규격 이름을 모른다(숫자 치수만 받는다). 규격마다 다른 **방법**(D790 은 탄성률을
 * 접선으로, ISO 178 은 현으로, ISO 7743 은 4번째 하중 구간)은 규격이 들고, 처리 화면이 시편의
 * 규격을 보고 기본 순서를 그것으로 채운다. 그 값을 고치는 자리다.
 *
 * 기준정보의 규격 치수 창이 자리를 내주고, 그리는 것은 처리 모듈이 한다 — 단계 · 옵션 · 선택지가
 * 처리의 것이다(`boundaries.test.ts`).
 *
 * **저장은 SI, 화면은 실무 단위**(처리 화면과 같은 표, `shared/units`). 빈 칸은 「비움」 이다 —
 * 굽힘의 하중 스팬을 비우면 3점이다.
 */

import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

import { processingApi } from '@/modules/processing/api'
import type { ProcessingStep, StepParam } from '@/modules/processing/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { useResource } from '@/shared/hooks/useResource'
import { axisLabel, fromDisplay, toDisplay } from '@/shared/units'

export type StandardDefaults = Record<string, Record<string, unknown>>

interface Props {
  value: StandardDefaults
  onChange: (next: StandardDefaults) => void
}

const selectClass = 'border-input bg-background h-7 rounded-md border px-1.5 text-xs'

/** 저장된 값(SI) → 칸에 보일 글자. */
function shownText(param: StepParam | undefined, value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'number' && param && (param.type === 'float' || param.type === 'int')) {
    return String(Number(toDisplay(value, param.unit, param.dimension).toPrecision(10)))
  }
  return String(value)
}

/** 칸의 글자 → 저장할 값. 빈 칸은 비움(`null`), `@` 는 참조, 수는 SI 로. */
function parsed(param: StepParam | undefined, text: string): unknown {
  const trimmed = text.trim()
  if (!trimmed) return null
  if (trimmed.startsWith('@')) return trimmed
  if (param && (param.type === 'float' || param.type === 'int')) {
    const number = Number(trimmed)
    // 수가 아니면 글자 그대로 보낸다 — 서버가 「수여야 합니다」 로 거절하고 이유를 말한다.
    return Number.isFinite(number) ? fromDisplay(number, param.unit, param.dimension) : trimmed
  }
  return trimmed
}

/** 옵션 하나의 값 칸 — 선택지면 고르고, 참/거짓이면 켬 · 끔, 나머지는 글자. */
function ValueField({
  param,
  value,
  label,
  onValue,
}: {
  param: StepParam | undefined
  value: unknown
  label: string
  onValue: (next: unknown) => void
}) {
  // **글자는 따로 들고 있는다.** 값에 매여 있으면 「0.」 을 치는 순간 「0」 으로 돌아간다.
  const [text, setText] = useState(() => shownText(param, value))
  if (param?.type === 'choice') {
    return (
      <select
        aria-label={label}
        className={selectClass}
        value={value === null || value === undefined ? '' : String(value)}
        onChange={(event) => onValue(event.target.value || null)}
      >
        <option value="">— 비움 —</option>
        {param.choices.map((choice) => (
          <option key={choice} value={choice}>
            {param.choice_labels?.[choice] ?? choice}
          </option>
        ))}
      </select>
    )
  }
  if (param?.type === 'bool') {
    return (
      <select
        aria-label={label}
        className={selectClass}
        value={value === true ? 'true' : value === false ? 'false' : ''}
        onChange={(event) =>
          onValue(event.target.value === '' ? null : event.target.value === 'true')
        }
      >
        <option value="">— 비움 —</option>
        <option value="true">켬</option>
        <option value="false">끔</option>
      </select>
    )
  }
  return (
    <Input
      aria-label={label}
      className="h-7 w-40 text-xs"
      placeholder="비움"
      value={text}
      onChange={(event) => {
        setText(event.target.value)
        onValue(parsed(param, event.target.value))
      }}
    />
  )
}

export function StandardDefaultsEditor({ value, onChange }: Props) {
  const [adding, setAdding] = useState(false)
  const [draftStep, setDraftStep] = useState('')
  const [draftOption, setDraftOption] = useState('')
  const count = Object.values(value).reduce((sum, one) => sum + Object.keys(one).length, 0)
  // **단계 목록은 필요할 때만 부른다** — 기본값이 있거나 더하려 할 때. 규격 창을 열 때마다
  // 처리 단계 전부를 부를 까닭이 없다.
  const needCatalog = adding || count > 0
  const catalog = useResource(
    () => (needCatalog ? processingApi.steps() : Promise.resolve([] as ProcessingStep[])),
    [needCatalog]
  )
  const byId = new Map((catalog.data ?? []).map((step) => [step.id, step]))
  /**
   * **목록이 온 뒤에 줄을 그린다.** 먼저 그리면 칸이 단위를 모른 채 SI 숫자(0.02 m)를 글자로
   * 잡아 두고, 목록이 온 뒤에도 그 글자가 남는다 — 라벨은 (mm) 인데 칸은 m 숫자다. 못 읽었으면
   * (오류) 원래 이름 · 값 그대로 보인다.
   */
  const ready = !needCatalog || catalog.data !== null || catalog.error !== null

  const rows = Object.entries(value).flatMap(([plugin, options]) =>
    Object.entries(options).map(([name, current]) => ({ plugin, name, current }))
  )

  function put(plugin: string, name: string, next: unknown) {
    onChange({ ...value, [plugin]: { ...(value[plugin] ?? {}), [name]: next } })
  }

  function remove(plugin: string, name: string) {
    const rest = { ...(value[plugin] ?? {}) }
    delete rest[name]
    const out = { ...value }
    if (Object.keys(rest).length) out[plugin] = rest
    else delete out[plugin]
    onChange(out)
  }

  const draftPlugin = byId.get(draftStep)
  const taken = new Set(Object.keys(value[draftStep] ?? {}))
  const draftParams = (draftPlugin?.params ?? []).filter(
    (param) => param.role !== 'column' && !taken.has(param.name)
  )

  return (
    <div className="space-y-1.5">
      <ErrorNotice error={catalog.error} />
      {!ready && <p className="text-muted-foreground text-xs">처리 단계를 읽는 중…</p>}
      {(ready ? rows : []).map(({ plugin, name, current }) => {
        const step = byId.get(plugin)
        const param = step?.params.find((one) => one.name === name)
        const label = `${step?.label ?? plugin} · ${
          param ? axisLabel(param.label, param.unit, param.dimension) : name
        }`
        return (
          <div key={`${plugin}:${name}`} className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="w-72">{label}</span>
            <ValueField
              param={param}
              value={current}
              label={label}
              onValue={(next) => put(plugin, name, next)}
            />
            <Button
              size="icon"
              variant="ghost"
              className="size-7"
              aria-label={`${label} 빼기`}
              onClick={() => remove(plugin, name)}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        )
      })}

      {adding ? (
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <select
            aria-label="더할 처리 단계"
            className={selectClass}
            value={draftStep}
            onChange={(event) => {
              setDraftStep(event.target.value)
              setDraftOption('')
            }}
          >
            <option value="">— 처리 단계 —</option>
            {(catalog.data ?? []).map((step) => (
              <option key={step.id} value={step.id}>
                {step.label}
              </option>
            ))}
          </select>
          <select
            aria-label="더할 옵션"
            className={selectClass}
            value={draftOption}
            disabled={!draftPlugin}
            onChange={(event) => setDraftOption(event.target.value)}
          >
            <option value="">— 옵션 —</option>
            {draftParams.map((param) => (
              <option key={param.name} value={param.name}>
                {param.label}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            disabled={!draftPlugin || !draftOption}
            onClick={() => {
              const param = draftPlugin?.params.find((one) => one.name === draftOption)
              // 처음 값은 그 옵션의 기본값 — 빈 칸에서 시작하면 「비움」 으로 저장된다.
              put(draftStep, draftOption, param?.default ?? null)
              setDraftOption('')
            }}
          >
            더하기
          </Button>
          <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setAdding(false)}>
            닫기
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => setAdding(true)}
          >
            <Plus className="size-3.5" />
            옵션 추가
          </Button>
          <span className="text-muted-foreground text-xs">
            {count
              ? '처리 화면이 이 규격의 시편을 열면 기본 순서를 이 값으로 채웁니다.'
              : '없으면 시험 종류의 기본 순서 그대로 깔립니다.'}
          </span>
        </div>
      )}
    </div>
  )
}
