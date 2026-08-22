/**
 * 표준 규격 가져오기 — **칸과 기호는 가져오고, 치수 값은 안 가져온다.**
 *
 * 규격 하나를 쓸모 있게 만들려면 칸을 만들고, 기호를 적고, 값을 넣고, 단면적
 * 식을 고르는 네 단계를 손으로 해야 한다. 규격이 스물이면 여든 번이다.
 *
 * ## 숫자를 왜 안 가져오는가
 *
 * 근거 문서가 **본문이 유료라 2차 출처 기반**이고 스스로 그렇게 적어 두었다.
 * 실제로 출처끼리 어긋난 곳이 있다(D5766 전체 길이가 152 mm 와 250 mm 로).
 * **그 숫자를 심으면 검증 안 된 값이 시스템의 정본이 된다** — 치수는 자릿수
 * 하나만 틀려도 응력이 통째로 어긋나는데 숫자는 그럴듯해 보인다.
 *
 * 칸과 기호는 그런 위험이 없다. 판이 바뀌어도 `게이지 길이 = G` 는 그대로다.
 *
 * ## 골라서 가져온다
 *
 * 배포할 때 전부 심지 않는 이유는, **안 쓰는 규격이 목록을 채우면 피커가
 * 무거워지기** 때문이다. 시편 분류처럼 몇 개 안 되는 것과 다르다 — 규격은
 * 부서마다 쓰는 것이 다르다.
 */

import { useMemo, useState } from 'react'
import { Download } from 'lucide-react'

import { vocabularyApi } from '@/modules/vocabulary/api'
import type { StandardTemplate } from '@/modules/vocabulary/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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
import { useResource } from '@/shared/hooks/useResource'

export function StandardCatalogDialog({
  onClose,
  onImported,
}: {
  onClose: () => void
  onImported: () => void
}) {
  const catalog = useResource(() => vocabularyApi.standardCatalog(), [])
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [made, setMade] = useState<number | null>(null)

  const families = useMemo(() => {
    const groups = new Map<string, StandardTemplate[]>()
    for (const item of catalog.data ?? []) {
      const list = groups.get(item.family) ?? []
      list.push(item)
      groups.set(item.family, list)
    }
    return [...groups]
  }, [catalog.data])

  function toggle(key: string) {
    setPicked((now) => {
      const next = new Set(now)
      if (!next.delete(key)) next.add(key)
      return next
    })
  }

  async function bring() {
    setBusy(true)
    setError(null)
    try {
      const result = await vocabularyApi.importStandards([...picked])
      setMade(result.length)
      setPicked(new Set())
      catalog.reload()
      onImported()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('가져오지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>표준 규격 가져오기</DialogTitle>
          <DialogDescription>
            <b>칸과 기호만 가져옵니다. 치수 값은 규격서를 보고 넣으세요.</b> 근거 문서가
            2차 출처라, 숫자를 그대로 심으면 검증 안 된 값이 정본이 됩니다 — 판이 바뀌어도
            칸과 기호는 그대로지만 값은 바뀝니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={catalog.error ?? error} />

        {made !== null && (
          <p className="rounded-md border p-2.5 text-xs">
            {made === 0 ? (
              <>이미 있는 이름이라 아무것도 안 만들었습니다 — 있는 값은 덮지 않습니다.</>
            ) : (
              <>
                <b>{made}개</b>를 만들었습니다. 각 규격의 <b>치수</b>에서 값을 넣으세요.
              </>
            )}
          </p>
        )}

        <div className="space-y-4">
          {families.map(([family, items]) => (
            <div key={family} className="space-y-1">
              <p className="text-muted-foreground text-xs font-semibold">{family}</p>
              {items.map((item) => (
                <label
                  key={item.key}
                  className={`hover:bg-muted/40 flex cursor-pointer items-start gap-2 rounded p-1.5 text-sm ${
                    item.taken ? 'opacity-50' : ''
                  }`}
                >
                  <input
                    type="checkbox"
                    className="mt-1"
                    aria-label={item.value}
                    disabled={item.taken}
                    checked={picked.has(item.key)}
                    onChange={() => toggle(item.key)}
                  />
                  <span className="flex-1">
                    <span className="flex flex-wrap items-center gap-1.5">
                      {item.value}
                      {/* **이미 있으면 안 덮는다** — 사람이 넣어 둔 치수가 사라진다. */}
                      {item.taken && (
                        <Badge variant="outline" className="text-xs">
                          이미 있음
                        </Badge>
                      )}
                      <span className="text-muted-foreground text-xs">
                        {item.category} · 칸 {item.fields.length}개
                        {item.ratio_checks.length > 0 &&
                          ` · 비율 조건 ${item.ratio_checks.length}개`}
                      </span>
                    </span>
                    {item.help && (
                      <span className="text-muted-foreground block text-xs">{item.help}</span>
                    )}
                    {/* 기호를 미리 보여 준다 — 같은 글자가 규격마다 다른 뜻이라,
                        무엇이 들어오는지 가져오기 전에 아는 편이 낫다. */}
                    <span className="text-muted-foreground block font-mono text-xs">
                      {item.fields
                        .map((one) => (one.symbol ? `${one.label} ${one.symbol}` : one.label))
                        .join(' · ')}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          ))}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
          <Button onClick={() => void bring()} disabled={busy || picked.size === 0}>
            <Download className="size-3.5" />
            {picked.size > 0 ? `${picked.size}개 가져오기` : '가져오기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
