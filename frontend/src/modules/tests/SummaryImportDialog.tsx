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
 */

import { useMemo, useState } from 'react'

import { testsApi } from '@/modules/tests/api'
import type { SummaryImport } from '@/modules/tests/api'
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
  testType,
  testTypeLabel,
  onClose,
  onDone,
}: {
  sampleId: string
  sampleName: string
  testType: string
  testTypeLabel: string
  onClose: () => void
  onDone: () => void
}) {
  const [extra, setExtra] = useState('항복강도 (MPa), 인장강도 (MPa), 연신율 (%)')
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
        { sample_id: sampleId, test_type: testType, values: toLines(columns, rows) },
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

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="flex max-h-[85vh] max-w-4xl flex-col gap-3">
        <DialogHeader>
          <DialogTitle>표로 {testTypeLabel} 넣기</DialogTitle>
          <DialogDescription>
            <b>{sampleName}</b> 의 시편들입니다. 한 줄이 시험 하나가 되고, <b>곡선은
            없습니다</b> — 요약값이 답할 수 있는 데까지 쓰입니다(통계·카드 근거).
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={error} />

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
            <b>없는 시편 만들기</b>
            <span className="text-muted-foreground block">
              끄면 이 시료에 없는 시편을 가리킨 줄은 안 들어가고 이유를 말합니다. 켜면
              그 줄이 시편까지 만듭니다 — 오타 하나가 유령 시편이 됩니다.
            </span>
          </span>
        </label>

        <div className="min-h-0 flex-1 overflow-y-auto">
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
            미리 보기
          </Button>
          <Button onClick={() => void send(false)} disabled={busy || !filled}>
            넣기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
