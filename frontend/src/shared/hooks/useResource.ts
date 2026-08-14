/**
 * 목록·상세를 불러오는 공통 패턴.
 *
 * 화면마다 loading/error/reload 상태를 다시 쓰면 그때마다 조금씩 달라지고,
 * "왜 이 화면만 오류가 안 보이지" 같은 차이가 생긴다. 한 곳에 둔다.
 */

import { useCallback, useEffect, useState } from 'react'

import { ApiError } from '@/shared/api/client'

interface Resource<T> {
  data: T | null
  error: ApiError | Error | null
  loading: boolean
  reload: () => void
}

export function useResource<T>(loader: () => Promise<T>, deps: unknown[] = []): Resource<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)

  // deps 는 호출부가 주는 값들이라 훅이 그 내용을 알 수 없다.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(loader, deps)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    run()
      .then((value) => {
        if (!cancelled) {
          setData(value)
          setError(null)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [run, tick])

  const reload = useCallback(() => setTick((value) => value + 1), [])

  return { data, error, loading, reload }
}
