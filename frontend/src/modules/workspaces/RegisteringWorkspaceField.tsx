/**
 * **등록 부서** — 정의를 어느 부서 이름으로 올리나(ADR 0035 3단계).
 *
 * 권한이 아니다. 고치는 사람은 등록자 · 편집을 받은 부서 · 자료 관리자다 — 전에는 이
 * 칸이 「전역이면 시스템 관리자, 부서면 그 부서 관리자」 로 고칠 사람을 정했고, 그래서
 * **부서 관리자인 부서만** 고를 수 있었다. 이제 내가 속한 부서면 된다(기본은 소속).
 *
 * 남은 뜻은 **장비 파일 자동 추정**이다: 내 부서가 올린 것과 부서 없이 올린 것만 대 본다.
 * 그래서 **부서 없이** 는 자료 관리자만 고른다 — 모든 부서의 파일 읽기를 바꾸는 자리다.
 */

import { useAuth } from '@/shared/auth/AuthContext'
import { isDataSteward } from '@/shared/auth/roles'
import { defaultRegisteringSlug } from '@/modules/workspaces/registering'
import { WorkspacePicker } from '@/modules/workspaces/WorkspacePicker'

export function RegisteringWorkspaceField({
  value,
  onChange,
  autoDetect = false,
}: {
  /** 부서 slug. `null` 이면 **부서 없이** — 자료 관리자만 고른다. */
  value: string | null
  onChange: (slug: string | null) => void
  /** 장비 파일 정의처럼 자동 추정의 범위가 되는 정의인가 — 안내 문구가 갈린다. */
  autoDetect?: boolean
}) {
  const { user } = useAuth()
  const memberships = user?.memberships ?? []
  const steward = isDataSteward(user)
  const none = value === null
  return (
    <div className="space-y-1.5">
      <WorkspacePicker
        workspaces={memberships}
        value={value}
        onChange={onChange}
        disabled={none}
        placeholder={none ? '부서 없이' : '부서를 고르세요'}
        className="w-full"
        emptyLabel="소속된 부서가 없습니다"
      />
      {steward && (
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={none}
            onChange={(event) =>
              onChange(event.target.checked ? null : defaultRegisteringSlug(user))
            }
          />
          부서 없이 올린다
          {autoDetect && ' — 모든 부서의 자동 추정에 쓰입니다'}
        </label>
      )}
      <p className="text-muted-foreground text-xs">
        등록 부서는 권한이 아닙니다 — 고치는 사람은 등록자(나)와, 내가 「권한」 에서 편집을
        준 부서, 자료 관리자입니다.
        {autoDetect &&
          ' 파일을 자동으로 읽을 때는 올린 사람 부서의 정의와 부서 없이 올린 정의만 대 봅니다.'}
      </p>
    </div>
  )
}
