/**
 * 오류 표시.
 *
 * **오류 코드와 요청 ID를 반드시 보여 준다.** 사용자가 그 문자열을 그대로 전달하면
 * 관리자가 로그에서 해당 요청을 찾을 수 있다(ADR 0001). 화면마다 다르게 만들면
 * 어떤 화면에서는 코드가 안 보여서 재현이 막힌다.
 */

import { AlertCircle } from 'lucide-react'

import { ApiError } from '@/shared/api/client'

interface ErrorNoticeProps {
  error: ApiError | Error | null
  className?: string
}

export function ErrorNotice({ error, className }: ErrorNoticeProps) {
  if (!error) return null

  const isApi = error instanceof ApiError
  return (
    <div
      className={`border-destructive/40 bg-destructive/5 text-destructive flex items-start gap-2 rounded-md border p-3 text-sm ${className ?? ''}`}
    >
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0">
        <p>{error.message}</p>
        {isApi && (
          <p className="mt-1 font-mono text-xs opacity-70">
            {error.code}
            {error.requestId ? ` · ${error.requestId}` : ''}
          </p>
        )}
      </div>
    </div>
  )
}
