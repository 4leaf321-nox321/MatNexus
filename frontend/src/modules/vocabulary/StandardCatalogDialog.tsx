/**
 * 표준 규격 가져오기 — **구조는 확실하고, 값은 시작점이다.**
 *
 * 규격 하나를 쓸모 있게 만들려면 칸을 만들고, 기호를 적고, 값을 넣고, 단면적
 * 식을 고르는 네 단계를 손으로 해야 한다. 규격이 스물이면 여든 번이다.
 *
 * ## 값은 딱 정해진 것만 온다
 *
 * 같은 치수표 안에서도 성격이 섞여 있다 — `G 200.0 ± 0.2` 는 고정값이지만
 * `R ≥ 25` 는 최소값, `C ≈ 50` 은 근사, 두께는 재료가 정한다. **최소값을 공칭
 * 으로 심으면 그 값이 그 규격의 치수인 척하게 된다.** 그래서 고정값만 온다.
 *
 * ## 그 값도 정본은 아니다
 *
 * 근거 문서가 **본문이 유료라 2차 출처 기반**이고 스스로 그렇게 적어 두었다.
 * 출처끼리 어긋난 곳도 있어서(D5766 전체 길이가 152 mm 와 250 mm 로) 그런
 * 항목은 아예 안 심었다. 관리자가 규격서를 보고 고치는 것을 전제한다.
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
import { Input } from '@/shared/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
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
  /**
   * 이미 있는 규격을 **다른 이름으로** 한 벌 더 만들 때 쓸 이름.
   *
   * **이 기능이 가장 값을 하는 자리다** — 같은 규격을 부서가 자기 치수로 쓰는
   * 경우다. 규격서가 범위나 최소만 주는 칸이 많아서 실제 값은 부서마다 갈린다.
   * 그때 **이름이 그 차이를 말해야 한다**: `ASTM E8/E8M 박판형` 이 둘이면 시편에
   * 붙은 이름만 보고는 어느 것이 무엇인지 알 수 없다.
   */
  const [renames, setRenames] = useState<Record<string, string>>({})
  /**
   * 지금 보고 있는 갈래.
   *
   * **목록이 오기 전에는 갈래를 모른다.** `defaultValue` 로 두면 그때의 빈 값이
   * 그대로 굳어서, 데이터가 온 뒤에도 아무 탭도 안 열린다.
   */
  const [tab, setTab] = useState('')
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

  /**
   * **이미 있는 것은 세지도 고르지도 않는다.** 덮지 않으므로 골라 봐야 아무 일도
   * 안 일어나는데, 개수에 섞이면 "12개 가져오기" 를 눌렀는데 3개만 생긴다.
   */
  const selectable = (items: StandardTemplate[]) => items.filter((one) => !one.taken)

  /** 이미 있는 것을 골랐다면 새 이름이 있어야 한다. */
  const needsName = (item: StandardTemplate) =>
    item.taken && picked.has(item.key) && !(renames[item.key] ?? '').trim()
  const blocked = (catalog.data ?? []).some(needsName)

  function toggle(key: string) {
    setPicked((now) => {
      const next = new Set(now)
      if (!next.delete(key)) next.add(key)
      return next
    })
  }

  /** 한 묶음을 통째로 켜고 끈다. 다 켜져 있으면 끄는 쪽이 된다. */
  function toggleMany(items: StandardTemplate[]) {
    const keys = selectable(items).map((one) => one.key)
    setPicked((now) => {
      const next = new Set(now)
      if (keys.every((key) => next.has(key))) keys.forEach((key) => next.delete(key))
      else keys.forEach((key) => next.add(key))
      return next
    })
  }

  const everything = selectable(catalog.data ?? [])
  const allPicked = everything.length > 0 && everything.every((one) => picked.has(one.key))

  async function bring() {
    setBusy(true)
    setError(null)
    try {
      const result = await vocabularyApi.importStandards(
        [...picked].map((key) => {
          const name = (renames[key] ?? '').trim()
          return name ? { key, value: name } : { key }
        })
      )
      setMade(result.length)
      setPicked(new Set())
      setRenames({})
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
      {/* **버튼이 스크롤 아래로 내려가면 안 된다.** 창 전체를 굴리면 고른 뒤
          가져오기를 찾으러 다시 내려가야 한다 — 목록만 구르고 머리와 발은 붙박이다. */}
      <DialogContent className="flex max-h-[85vh] flex-col gap-3 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>표준 규격 가져오기</DialogTitle>
          <DialogDescription>
            칸·기호·단면적 식과 <b>규격이 딱 정해 둔 값</b>을 가져옵니다. 최소값
            (R ≥ 25)·범위·근사·재료가 정하는 두께는 빈 칸으로 옵니다.{' '}
            <b>값은 시작점이지 정본이 아닙니다</b> — 근거가 2차 출처라 규격서로 확인하고
            고쳐 쓰세요.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={catalog.error ?? error} />

        {/* **스물여덟 줄을 하나씩 누르게 하지 않는다.** 처음 도입할 때는 한
            갈래를 통째로 가져오는 것이 보통이다. */}
        {everything.length > 0 && (
          <div className="flex items-center gap-2 border-b pb-2">
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={() => toggleMany(catalog.data ?? [])}
            >
              {allPicked ? '전체 지우기' : '전체 고르기'}
            </Button>
            <span className="text-muted-foreground text-xs">
              {picked.size > 0
                ? `${picked.size}개 골랐습니다 (고를 수 있는 것 ${everything.length}개)`
                : `고를 수 있는 것 ${everything.length}개`}
            </span>
          </div>
        )}

        {made !== null && (
          <p className="rounded-md border p-2.5 text-xs">
            {made === 0 ? (
              <>이미 있는 이름이라 아무것도 안 만들었습니다 — 있는 값은 덮지 않습니다.</>
            ) : (
              <>
                <b>{made}개</b>를 만들었습니다. 각 규격의 <b>치수</b>에서 값을 확인하고,
                빈 칸을 채우세요.
              </>
            )}
          </p>
        )}

        {/* **세로로 스물여덟 줄을 늘어놓지 않는다.** 갈래가 넷인데 한 번에 보는
            것은 하나다 — 금속을 고르는 사람에게 DMA 아홉 줄은 방해다.

            탭 이름에 **고른 개수를 함께 적는다.** 탭을 옮기면 앞서 고른 것이
            안 보이는데, 그러면 "몇 개 고르기" 버튼의 숫자와 눈앞이 어긋난다. */}
        <Tabs
          value={tab || (families[0]?.[0] ?? '')}
          onValueChange={setTab}
          className="min-h-0 flex-1"
        >
          <TabsList>
            {families.map(([family, items]) => {
              const chosen = items.filter((one) => picked.has(one.key)).length
              return (
                <TabsTrigger
                  key={family}
                  value={family}
                  /* 눈에는 `2/5` 로 짧게, 읽어 주는 쪽에는 말로. 숫자만 읽으면
                     그게 개수인지 순번인지 알 수 없다. */
                  aria-label={
                    chosen > 0
                      ? `${family} — ${selectable(items).length}개 중 ${chosen}개 고름`
                      : `${family} — ${items.length}개`
                  }
                >
                  {family}
                  <span className="text-muted-foreground ml-1 text-xs">
                    {chosen > 0 ? `${chosen}/${selectable(items).length}` : items.length}
                  </span>
                </TabsTrigger>
              )
            })}
          </TabsList>

          {families.map(([family, items]) => (
            <TabsContent key={family} value={family} className="min-h-0 space-y-1">
              {selectable(items).length > 0 &&
                (() => {
                  const on = selectable(items).every((one) => picked.has(one.key))
                  return (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs"
                      /* **이름이 동작을 따라가야 한다.** 고정해 두면 다 켠 뒤에도
                         '고르기' 로 읽힌다 — 화면 낭독기가 그 거짓말을 듣는다. */
                      aria-label={`${family} 묶음 ${on ? '지우기' : '고르기'}`}
                      onClick={() => toggleMany(items)}
                    >
                      {on ? '묶음 지우기' : '묶음 고르기'}
                    </Button>
                  )
                })()}
              <div className="max-h-[46vh] space-y-1 overflow-y-auto pr-1">
              {items.map((item) => (
                <label
                  key={item.key}
                  className="hover:bg-muted/40 flex cursor-pointer items-start gap-2 rounded p-1.5 text-sm"
                >
                  <input
                    type="checkbox"
                    className="mt-1"
                    aria-label={item.value}
                    checked={picked.has(item.key)}
                    onChange={() => toggle(item.key)}
                  />
                  <span className="flex-1">
                    <span className="flex flex-wrap items-center gap-1.5">
                      {item.value}
                      {/* **이미 있으면 안 덮는다** — 사람이 넣어 둔 치수가 사라진다. */}
                      {item.taken && (
                        <Badge variant="outline" className="text-xs">
                          이미 있음 · 다른 이름 필요
                        </Badge>
                      )}
                      <span className="text-muted-foreground text-xs">
                        {item.category} · 칸 {item.fields.length}개
                        {/* **값이 오는지 아닌지가 고르는 판단을 바꾼다.** 값이
                            없는 규격은 가져와도 숫자를 다 넣어야 한다. */}
                        {Object.keys(item.attributes).length > 0
                          ? ` · 값 ${Object.keys(item.attributes).length}개 포함`
                          : ' · 값 없음'}
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
                    {/* **같은 이름으로는 못 넣는다.** 규격 이름은 시편까지 따라
                        내려가므로, 둘이 같으면 어느 것이 무엇인지 알 수 없다. */}
                    {item.taken && picked.has(item.key) && (
                      <Input
                        aria-label={`${item.value} 새 이름`}
                        placeholder={`${item.value} (사내 A)`}
                        className="mt-1 h-7 text-xs"
                        value={renames[item.key] ?? ''}
                        onClick={(event) => event.preventDefault()}
                        onChange={(event) =>
                          setRenames((now) => ({ ...now, [item.key]: event.target.value }))
                        }
                      />
                    )}
                  </span>
                </label>
              ))}
              </div>
            </TabsContent>
          ))}
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
          <Button onClick={() => void bring()} disabled={busy || picked.size === 0 || blocked}>
            <Download className="size-3.5" />
            {picked.size > 0 ? `${picked.size}개 가져오기` : '가져오기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
