/**
 * 해석용 물성 정의 목록 — **지금 어떤 솔버로 내보낼 수 있나.**
 *
 * 인풋 파일 정의가 「장비 파일을 어떻게 읽나」 라면 여기는 그 반대다 — 물성 카드를
 * 어떤 솔버 덱으로 쓰나. 둘 다 **코드가 아니라 데이터**이고, 그래서 새 솔버를
 * 붙이는 데 배포가 필요 없다(ADR 0023).
 *
 * **코드로 만든 형식은 여기 안 뜬다.** Abaqus·OpenRadioss·JSON 은 검증과 분기가
 * 있어 코드에 남아 있고, 이 화면은 정의로 붙인 것만 다룬다 — 지울 수 있는 것과
 * 없는 것을 한 표에 섞으면 지우기가 왜 안 되는지 화면에 안 나온다.
 */

import { useRef, useState } from 'react'
import { Download, FileOutput, Globe2, Pencil, Plus, Trash2, Upload } from 'lucide-react'
import { Link } from 'react-router-dom'

import { ImportProfilesDialog } from '@/modules/fitting/ImportProfilesDialog'
import { fittingApi } from '@/modules/fitting/api'
import type { ExportProfile } from '@/modules/fitting/api'
import {
  ProfileFileError,
  fileNameFor,
  makeFile,
  readProfileFile,
  saveProfileFile,
  toFileEntry,
} from '@/modules/fitting/profileFile'
import type { ProfileInFile } from '@/modules/fitting/profileFile'
import { useAuth } from '@/shared/auth/AuthContext'
import { isAnyManager } from '@/shared/auth/roles'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'

export default function ExportProfilesPage() {
  const canEdit = isAnyManager(useAuth().user)
  const profiles = useResource(() => fittingApi.exportProfiles(), [])
  const [error, setError] = useState<Error | null>(null)
  const [said, setSaid] = useState<string | null>(null)
  const [incoming, setIncoming] = useState<ProfileInFile[] | null>(null)
  const picker = useRef<HTMLInputElement>(null)
  const rows = profiles.data ?? []

  /** 파일로 내보낸다. 목록이 정의 전체를 이미 들고 있어 서버를 안 거친다. */
  function save(items: ExportProfile[]) {
    const entries = items.map((one) =>
      toFileEntry({ ...one, definition: one.definition as Record<string, unknown> })
    )
    saveProfileFile(makeFile(entries, window.location.host), fileNameFor(entries))
  }

  async function pick(file: File) {
    setError(null)
    setSaid(null)
    try {
      setIncoming(readProfileFile(await file.text()))
    } catch (caught) {
      // **못 읽은 이유를 그대로 보인다.** 「불러오지 못했습니다」 만으로는 파일을
      // 고쳐야 하는지 다른 파일을 골라야 하는지 모른다.
      setError(
        caught instanceof ProfileFileError ? caught : new Error('파일을 읽지 못했습니다.')
      )
    }
  }

  async function remove(item: ExportProfile) {
    setError(null)
    try {
      await fittingApi.removeExportProfile(item.key)
      profiles.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
    }
  }

  return (
    <div>
      <PageHeader
        title="해석용 물성 정의"
        description="물성 카드를 어느 솔버의 입력으로 쓸지. 키워드 이름·차례·칸 폭을 여기에 저장합니다 — 새 솔버를 붙이는 데 배포가 필요 없습니다."
        actions={
          // **볼 수는 있어도 고치는 것은 부서 관리자다.** 목록을 모두에게 연 것은
          // 「우리가 어떤 솔버로 낼 수 있나」 를 누구나 물어야 해서다.
          canEdit ? (
            <span className="flex flex-wrap gap-2">
              {/* **개발 서버에서 만들어 운영으로 옮기는 길이다.** 정의는 코드가
                  아니라 데이터라(ADR 0023) 배포 없이 붙는데, 그러면 서버 사이를
                  옮기는 길도 있어야 한다 — 없으면 운영에서 손으로 다시 만든다. */}
              <Button
                variant="outline"
                disabled={rows.length === 0}
                onClick={() => save(rows)}
                title={
                  rows.length === 0
                    ? '내보낼 정의가 없습니다'
                    : `${rows.length}건을 JSON 파일 하나로`
                }
              >
                <Download className="size-4" />
                전부 내보내기
              </Button>
              <Button variant="outline" onClick={() => picker.current?.click()}>
                <Upload className="size-4" />
                불러오기
              </Button>
              <input
                ref={picker}
                type="file"
                accept="application/json,.json"
                className="hidden"
                aria-label="물성 정의 파일"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  // **같은 파일을 다시 고를 수 있어야 한다.** 값을 안 비우면
                  // 두 번째 선택에서 change 가 안 난다.
                  event.target.value = ''
                  if (file) void pick(file)
                }}
              />
              <Button asChild>
                <Link to="/settings/export-profiles/new">
                  <Plus className="size-4" />
                  정의 만들기
                </Link>
              </Button>
            </span>
          ) : null
        }
      />

      {said ? (
        <div className="mb-4 rounded-md border border-emerald-500/40 bg-emerald-500/5 p-3 text-sm">
          들여왔습니다 — <b>{said}</b>
        </div>
      ) : null}
      {error ? <ErrorNotice error={error} className="mb-4" /> : null}
      {profiles.error ? <ErrorNotice error={profiles.error} className="mb-4" /> : null}

      {rows.length === 0 && !profiles.loading ? (
        <p className="text-muted-foreground rounded-md border border-dashed p-6 text-sm">
          아직 정의가 없습니다. Abaqus·OpenRadioss·중립 JSON 은 코드로 만들어져 있어
          여기 없어도 내보낼 수 있습니다 — 그 밖의 솔버를 여기에 더합니다.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>key</TableHead>
              <TableHead>이름</TableHead>
              <TableHead>확장자</TableHead>
              <TableHead>소유</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="font-mono text-xs">{item.key}</TableCell>
                <TableCell>
                  <span className="flex items-center gap-2">
                    <FileOutput className="text-muted-foreground size-4" />
                    {item.label}
                    {item.is_active ? null : <Badge variant="outline">중단</Badge>}
                  </span>
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {String(
                    (item.definition as Record<string, unknown>).extension ?? '?'
                  )}
                </TableCell>
                <TableCell>
                  {/* **전역은 여러 부서가 함께 쓴다.** 한 부서가 고치면 남의 덱이
                      바뀌므로, 어느 쪽인지 표에서 바로 보여야 한다. */}
                  {item.is_global ? (
                    <Badge variant="secondary">
                      <Globe2 className="size-3" />
                      전역
                    </Badge>
                  ) : (
                    <span className="text-muted-foreground text-sm">
                      {item.owner_workspace_name ?? '내 부서'}
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  {canEdit ? (
                    <span className="flex justify-end gap-1">
                      {/* **한 벌만 옮기는 것이 흔한 일이다** — 방금 만든 이것을
                          운영으로 보낸다. 전부 내보내고 파일을 손으로 자르게 하지
                          않는다. */}
                      <Button
                        variant="ghost"
                        size="icon"
                        title="파일로 내보내기"
                        onClick={() => save([item])}
                      >
                        <Download className="size-4" />
                      </Button>
                      <Button variant="ghost" size="icon" asChild title="고치기">
                        <Link to={`/settings/export-profiles/${item.key}`}>
                          <Pencil className="size-4" />
                        </Link>
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        title="지우기"
                        onClick={() => void remove(item)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </span>
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <ImportProfilesDialog
        incoming={incoming}
        existing={new Set(rows.map((one) => one.key))}
        onClose={() => setIncoming(null)}
        onDone={(message) => {
          setIncoming(null)
          setSaid(message)
          profiles.reload()
        }}
      />
    </div>
  )
}
