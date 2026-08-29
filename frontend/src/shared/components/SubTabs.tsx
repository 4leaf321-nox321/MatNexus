/**
 * 경로로 갈리는 탭 — **한 진입점 아래 여러 화면.**
 *
 * 사이드바 항목 하나가 화면 둘을 덮어야 할 때 쓴다. 공지와 VOC 가 그랬다:
 * 하나는 위에서 내려오는 글이고 하나는 아래에서 올라가는 글이라 **사람에게는 같은
 * 게시판**인데, 메뉴에 둘로 서 있으면 「어느 쪽에 쓰지」 를 매번 묻게 된다.
 *
 * **주소는 그대로 둔다.** 탭 상태를 화면 안에 감추면 링크로 가리킬 수 없다 —
 * 공지 하나를 남에게 보낼 때 「공지 탭을 눌러라」 를 덧붙여야 한다. 여기서는 탭이
 * 곧 경로라 붙여 넣은 주소가 그 탭을 연다.
 */

import { useLocation, useNavigate } from 'react-router-dom'

import { Tabs, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'

export interface SubTab {
  to: string
  label: string
}

export function SubTabs({ items }: { items: SubTab[] }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  // 하위 경로(`/guide/xxx`)에서도 그 탭이 켜져 있어야 한다 — 정확히 같을 때만
  // 켜면 상세로 들어간 순간 아무 탭도 안 켜지고 「길을 잃은」 화면이 된다.
  const current =
    items.find((item) => pathname === item.to)?.to ??
    items.find((item) => pathname.startsWith(`${item.to}/`))?.to ??
    items[0]?.to

  return (
    <Tabs value={current} onValueChange={(value) => navigate(value)} className="mb-4">
      <TabsList>
        {items.map((item) => (
          <TabsTrigger key={item.to} value={item.to}>
            {item.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}
