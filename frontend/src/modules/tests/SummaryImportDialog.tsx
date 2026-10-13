/**
 * 시험 요약표 흡수 — **곡선 없이 값만 들어온다.**
 *
 * 기존 앱이 내보낸 표는 **한 줄이 시험 하나**이고 곡선이 없다. 곡선이 없다고 못
 * 쓰는 데이터가 아니다 — 통계도 되고 카드의 근거도 된다. 안 되는 것은 곡선을
 * 다시 처리하는 일뿐이다.
 *
 * ## 어느 시료인지는 사람이 고른다
 *
 * 표에는 시편번호가 있고 **재료 이름이 없다** — 한 파일이 대개 한 시료 분이기
 * 때문이다. 그래서 이 창은 시료에서 연다.
 *
 * ## 없는 시편을 만들지 말지는 옵션
 *
 * 만들면 편하지만 오타 하나가 유령 시편을 만든다 — 기준정보에서 겪은 것과 같은
 * 병이다. 그래서 **기본은 끔**이고, 켰을 때는 미리보기가 어느 줄이 시편까지
 * 만드는지 줄마다 말한다.
 *
 * ## 시험 종류는 창에서 고른다 (2026-10-13)
 *
 * 전에는 시료 화면이 인장시험을 박아 넘겼다. 서버는 어느 종류든 받는데 화면에 길이 없어서,
 * **곡선 채널이 없는 피로 시험과 보고서의 최소 크리프 속도를 넣을 방법이 없었다** — v1.283
 * 공지는 크리프를 「표로 입력」 할 수 있다고 적었는데 사실이 아니었다. 종류를 고르면 기본 열이
 * 그 종류의 필수 조건과 **묶음이 읽는 요약값 키**로 바뀐다(열 이름이 곧 저장 키다).
 */

import { useMemo, useState } from 'react'

import { testsApi } from '@/modules/tests/api'
import type { SummaryImport, TestType } from '@/modules/tests/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PasteGrid, toLines } from '@/shared/components/PasteGrid'
import type { Column } from '@/shared/components/PasteGrid'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { useResource } from '@/shared/hooks/useResource'
import { axisLabel } from '@/shared/units'

/** 인장의 기본 열 — 옛 앱이 내보낸 요약표의 열 이름 그대로. */
const TENSILE_COLUMNS = '항복강도 (MPa), 인장강도 (MPa), 연신율 (%)'

/**
 * 종류마다 **묶음이 읽는 요약값 키.** 요약값은 열 이름이 곧 키라서, 이 이름이 아니면
 * 「S-N 곡선 (Basquin)」 · 「크리프 식 (Norton · Garofalo)」 묶음이 그 시험을 못 본다.
 */
const SUMMARY_KEYS: Record<string, { header: string; siUnit?: string }[]> = {
  fatigue: [{ header: 'cycles_to_failure' }, { header: 'runout' }],
  creep: [{ header: 'min_creep_rate', siUnit: '1/s' }],
}

const HINTS: Record<string, string> = {
  fatigue:
    '파단 수명은 cycles_to_failure, 런아웃이면 runout 에 1(아니면 비웁니다). 응력 진폭이 ' +
    '필수 조건입니다 — 「S-N 곡선 (Basquin)」 묶음이 이 값을 씁니다.',
  creep:
    '보고서의 최소 크리프 속도는 min_creep_rate 에 적습니다. 가한 응력 · 시험 온도가 필수 ' +
    '조건입니다 — 「크리프 식 (Norton · Garofalo)」 묶음이 이 값을 씁니다.',
}

/** 종류를 고르면 채우는 기본 열 — 필수 조건, 묶음이 읽는 요약값, 나머지 숫자 조건 순. */
export function defaultColumns(type: TestType | undefined): string {
  if (!type || type.key === 'tensile') return TENSILE_COLUMNS
  const numeric = type.conditions.filter((field) => field.value_type === 'number')
  const label = (field: TestType['conditions'][number]) =>
    axisLabel(field.label, field.si_unit, field.dimension)
  return [
    ...numeric.filter((field) => field.is_required).map(label),
    ...(SUMMARY_KEYS[type.key] ?? []).map((one) => axisLabel(one.header, one.siUnit)),
    ...numeric.filter((field) => !field.is_required).map(label),
  ].join(', ')
}

/**
 * 늘 있는 열.
 *
 * `원본 파일명` 이 없으면 **같은 표를 두 번 붙였을 때 막을 길이 없다** — 시험은
 * 한 시편에 여러 번 있을 수 있어서 시편만으로는 중복을 알 수 없다.
 */
const FIXED: Column[] = [
  { key: '시편', header: '시편', help: 'MD-1 이나 1' },
  { key: '방향', header: '방향' },
  { key: '원본 파일명', header: '원본 파일명', help: '같은 표를 두 번 넣는 것을 막는다' },
]

export function SummaryImportDialog({
  sampleId,
  sampleName,
  testType = 'tensile',
  onClose,
  onDone,
}: {
  sampleId: string
  sampleName: string
  /** 처음 고를 종류. 창 안에서 바꿀 수 있다. */
  testType?: string
  onClose: () => void
  onDone: () => void
}) {
  const types = useResource(() => testsApi.types(), [])
  const available = (types.data ?? []).filter((type) => type.is_active)
  const [typeKey, setTypeKey] = useState(testType)
  const selected = available.find((type) => type.key === typeKey)
  const typeLabel = selected?.label ?? (typeKey === 'tensile' ? '인장시험' : '시험')
  const [extra, setExtra] = useState(TENSILE_COLUMNS)
  const [rows, setRows] = useState<string[][]>([[]])
  const [createMissing, setCreateMissing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [preview, setPreview] = useState<SummaryImport | null>(null)
  const [done, setDone] = useState<SummaryImport | null>(null)

  /** 사람이 적은 열 이름. **표마다 다르고 미리 알 방법이 없다.** */
  const columns = useMemo(
    () => [
      ...FIXED,
      ...extra
        .split(',')
        .map((one) => one.trim())
        .filter(Boolean)
        .map((header) => ({ key: header, header })),
    ],
    [extra]
  )
  const filled = rows.filter((row) => row.some((cell) => cell.trim())).length

  async function send(dry: boolean) {
    setBusy(true)
    setError(null)
    setPreview(null)
    setDone(null)
    try {
      const answer = await testsApi.importSummaries(
        { sample_id: sampleId, test_type: typeKey, values: toLines(columns, rows) },
        { dry, createMissing }
      )
      if (dry) setPreview(answer)
      else {
        setDone(answer)
        setRows([[]])
        onDone()
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('넣지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const answer = done ?? preview

  /** 종류를 바꾸면 열도 그 종류의 것으로 — 인장의 열로 피로를 넣으면 묶음이 못 본다. */
  function pickType(key: string) {
    setTypeKey(key)
    setExtra(defaultColumns(available.find((type) => type.key === key)))
    setPreview(null)
    setDone(null)
  }

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="gap-3 sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>표로 {typeLabel} 입력</DialogTitle>
          <DialogDescription>
            <b>{sampleName}</b> 의 시편들입니다. 한 줄이 시험 하나가 되고, <b>곡선은
            없습니다</b> — 요약값이 답할 수 있는 데까지 쓰입니다(통계·카드 근거).
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={error ?? types.error} />

        {available.length > 1 && (
          <div className="space-y-1.5">
            <Label htmlFor="import-type">시험 종류</Label>
            <select
              id="import-type"
              className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
              value={typeKey}
              onChange={(event) => pickType(event.target.value)}
            >
              {available.map((type) => (
                <option key={type.key} value={type.key}>
                  {type.label}
                </option>
              ))}
            </select>
            {HINTS[typeKey] && <p className="text-muted-foreground text-xs">{HINTS[typeKey]}</p>}
          </div>
        )}

        <div className="space-y-1.5">
          <Label htmlFor="import-extra">요약값 열</Label>
          <Input
            id="import-extra"
            value={extra}
            onChange={(event) => setExtra(event.target.value)}
          />
          <p className="text-muted-foreground text-xs">
            쉼표로 나눠 적습니다. <b>숫자 열은 단위를 함께</b> — <code>항복강도 (MPa)</code>.
            시험 종류가 선언한 조건 이름을 적으면 조건으로 들어갑니다.
          </p>
        </div>

        {/* **켜 두면 표가 시편을 늘린다.** 오타 하나가 유령 시편을 만든다. */}
        <label className="flex items-start gap-2 text-xs">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={createMissing}
            onChange={(event) => {
              setCreateMissing(event.target.checked)
              setPreview(null)
            }}
          />
          <span>
            <b>없는 시편 생성</b>
            <span className="text-muted-foreground block">
              끄면 이 시료에 없는 시편을 가리킨 줄은 안 들어가고 이유를 말합니다. 켜면
              그 줄이 시편까지 만듭니다 — 오타 하나가 유령 시편이 됩니다.
            </span>
          </span>
        </label>

        <div>
          <PasteGrid columns={columns} rows={rows} onRows={setRows} required="시편" />
        </div>

        {answer && (
          <div className="space-y-1.5 rounded-md border p-2.5">
            <p className="text-sm">
              {done ? '넣었습니다' : '넣으면'} — 시험 <b>{answer.created}</b>
              {answer.specimens_created > 0 && ` · 시편 ${answer.specimens_created}`}
              {answer.existing > 0 && ` · 이미 있음 ${answer.existing}`}
              {answer.rejected > 0 && (
                <span className="text-amber-700 dark:text-amber-500">
                  {' '}
                  · 못 넣음 {answer.rejected}
                </span>
              )}
            </p>
            <div className="max-h-40 overflow-y-auto text-xs">
              <table className="w-full">
                <tbody>
                  {answer.items
                    .filter((item) => item.status !== 'skipped')
                    .map((item, index) => (
                      <tr key={index} className="border-t">
                        <td className="py-0.5 pr-2 whitespace-nowrap">
                          {item.status === 'new' && '넣음'}
                          {item.status === 'existing' && (
                            <span className="text-muted-foreground">이미 있음</span>
                          )}
                          {item.status === 'rejected' && (
                            <span className="text-amber-700 dark:text-amber-500">못 넣음</span>
                          )}
                        </td>
                        <td className="py-0.5 pr-2">
                          {item.run ?? item.specimen}
                          {/* **켜 두면 표가 시편을 늘린다** — 그 사실이 줄마다 보여야 한다. */}
                          {item.creates_specimen && (
                            <Badge variant="outline" className="ml-1 text-xs">
                              시편도 만듦
                            </Badge>
                          )}
                        </td>
                        <td className="text-muted-foreground py-0.5">
                          {item.reason}
                          {item.warnings.map((one, at) => (
                            <span key={at} className="block text-amber-700 dark:text-amber-500">
                              {one}
                            </span>
                          ))}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            닫기
          </Button>
          <Button variant="outline" onClick={() => void send(true)} disabled={busy || !filled}>
            미리보기
          </Button>
          <Button onClick={() => void send(false)} disabled={busy || !filled}>
            입력
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
