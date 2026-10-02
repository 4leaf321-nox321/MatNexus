/**
 * 해석용 물성 정의 목록 — **지금 어떤 솔버로 내보낼 수 있나.**
 *
 * 인풋 파일 정의가 「장비 파일을 어떻게 읽나」 라면 여기는 그 반대다 — 물성 카드를
 * 어떤 솔버 덱으로 쓰나. 둘 다 **코드가 아니라 데이터**이고, 그래서 새 솔버를
 * 붙이는 데 배포가 필요 없다(ADR 0023).
 *
 * **코드로 만든 형식은 정의 표에 안 섞는다.** 검증과 분기가 있어 코드에 남은 것들이고,
 * 지울 수 있는 것과 없는 것을 한 표에 섞으면 지우기가 왜 안 되는지 화면에 안 나온다.
 * 대신 아래에 따로 보인다(`BuiltinFormatsSection`) — 안 보이니 「이 솔버는 정의 하나뿐」
 * 으로 읽혔다(2026-09-27).
 */

import { useRef, useState } from 'react'
import { Download, FileOutput, Pencil, Plus, Power, Trash2, Upload } from 'lucide-react'
import { Link } from 'react-router-dom'

import { BuiltinFormatsSection } from '@/modules/fitting/BuiltinFormatsSection'
import { ImportProfilesDialog } from '@/modules/fitting/ImportProfilesDialog'
import { UnitSystemsSection } from '@/modules/fitting/UnitSystemsSection'
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
import { canEdit, lockedTitle } from '@/modules/ownership/access'
import { useAuth } from '@/shared/auth/AuthContext'
import { isSystemAdmin } from '@/shared/auth/roles'
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
  const { user } = useAuth()
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

  /**
   * 켜고 끈다. **정의판을 켜는데 짝인 코드판이 살아 있으면 묻는다** — 켜는 순간 내보내기 메뉴에
   * 같은 형식이 두 줄 선다. 보통은 코드판을 먼저 사용 중단하고 켠다(아래 「기본 제공 형식」).
   */
  async function toggle(item: ExportProfile) {
    setError(null)
    const turningOn = !item.is_active
    if (turningOn && item.twin_of && !item.twin_held) {
      const ok = window.confirm(
        `기본 형식 '${item.twin_of}' 이(가) 아직 쓰이고 있습니다. 이 정의판을 켜면 카드의 ` +
          `내보내기 메뉴에 같은 형식이 두 줄 섭니다.\n\n보통은 아래 「기본 제공 형식」 에서 ` +
          `'${item.twin_of}' 를 먼저 사용 중단합니다. 그래도 켤까요?`
      )
      if (!ok) return
    }
    try {
      await fittingApi.setExportProfileActive(item.key, turningOn)
      profiles.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('켜고 끄지 못했습니다.'))
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
          // **만들기·불러오기는 누구나다**(ADR 0035 3단계 — 전에는 부서 관리자였고, 그나마
          // 화면이 부서를 안 보내서 「전역」 으로 읽혀 403 이 났다). 올린 정의의 등록 부서는
          // 내 소속이다. 고치는 것은 줄마다 다르다(`access`).
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
                  정의 생성
                </Link>
              </Button>
            </span>
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
          아직 정의가 없습니다. 아래 「기본 제공 형식」 은 코드로 만들어져 있어 정의 없이도
          내보낼 수 있습니다 — 그 밖의 솔버나 부서의 덱 관례를 여기에 더합니다.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>key</TableHead>
              <TableHead>이름</TableHead>
              <TableHead>확장자</TableHead>
              <TableHead>등록 부서</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="font-mono">{item.key}</TableCell>
                <TableCell>
                  <span className="flex items-center gap-2">
                    <FileOutput className="text-muted-foreground size-4" />
                    {item.label}
                    {/* **「꺼짐」 이다 — 「사용 중단」 이 아니다.** 사용 중단은 기본 형식(코드판)을
                        내리는 말이라, 같은 말을 쓰면 둘이 섞인다. */}
                    {item.is_active ? null : <Badge variant="outline">꺼짐</Badge>}
                    {item.twin_of ? (
                      <Badge
                        variant="secondary"
                        title={`기본 형식 ${item.twin_of} 를 정의로 옮긴 비상용 사본 — 코드판을 사용 중단하면 이것을 켜서 고쳐 씁니다`}
                      >
                        정의판 · {item.twin_of}
                      </Badge>
                    ) : null}
                  </span>
                </TableCell>
                <TableCell className="font-mono">
                  {String(
                    (item.definition as Record<string, unknown>).extension ?? '?'
                  )}
                </TableCell>
                <TableCell>
                  {/* 등록한 부서 — 권한이 아니다(ADR 0035). 누가 고치는지는 편집기가 말한다. */}
                  {item.owner_workspace_name ?? '부서 없음'}
                </TableCell>
                <TableCell className="text-right">
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
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`${item.label} ${item.is_active ? '끄기' : '켜기'}`}
                        disabled={!canEdit(item.access)}
                        title={
                          lockedTitle(item.access) ??
                          (item.is_active
                            ? '끄기 — 내보내기 메뉴에서 뺍니다'
                            : '켜기 — 내보내기 메뉴에 세웁니다')
                        }
                        className={item.is_active ? 'text-emerald-600' : 'text-muted-foreground'}
                        onClick={() => void toggle(item)}
                      >
                        <Power className="size-4" />
                      </Button>
                      {/* **여는 것은 누구나** — 편집기가 읽기로 열고 누가 고치는지 말한다. */}
                      <Button
                        variant="ghost"
                        size="icon"
                        asChild
                        title={canEdit(item.access) ? '편집' : '보기'}
                      >
                        <Link to={`/settings/export-profiles/${item.key}`}>
                          <Pencil className="size-4" />
                        </Link>
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        disabled={!canEdit(item.access)}
                        title={lockedTitle(item.access) ?? '삭제'}
                        onClick={() => void remove(item)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                  </span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {/* 코드로 만든 형식 — 정의와 섞지 않고 따로. 멈춘 것도 사연과 함께 선다. */}
      <BuiltinFormatsSection
        twins={Object.fromEntries(
          rows.filter((one) => one.twin_of).map((one) => [one.twin_of as string, one])
        )}
        onToggleTwin={toggle}
      />

      {/* **단위계는 전사가 같은 것을 봐야 한다** — 만드는 것은 시스템 관리자다.
          정의(솔버 형식)와 한 화면에 두는 이유: 덱을 내려받을 때 둘을 함께 고른다. */}
      <UnitSystemsSection canEdit={isSystemAdmin(user)} />

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
