/**
 * 복합 물성 — 영역의 홈이자, **지금은 설계 논의의 자리.**
 *
 * 화면이 하나도 없는 영역에 스위치만 두면 「고장난 것」 처럼 보인다. 그래서 이
 * 화면이 먼저 선다 — 이 영역이 재료 물성과 무엇이 다른지, 어떤 화면이 어느
 * 단계에 오는지, 그 전에 무엇을 확인해야 하는지. 사이드바의 항목 목록
 * (`navigation.ts`)을 그대로 읽으므로, 메뉴와 이 화면이 서로 다른 말을 할 수 없다.
 *
 * 스키마는 ADR 0026 이 제안이고, MX 의 현행 시험 데이터 체계를 확인한 뒤 확정된다.
 * **그 전에 만드는 화면은 짐작이다** — 그래서 여기 있는 것은 자리뿐이다.
 */

import { ArrowRight, Construction } from 'lucide-react'
import { Link } from 'react-router-dom'

import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { realmGroups } from '@/shared/layout/navigation'

/** 재료 물성과 무엇이 다른가. 이 표가 「왜 영역을 나눴나」 의 근거다. */
const CONTRAST: { what: string; material: string; composite: string }[] = [
  { what: '대상', material: '재료 하나', composite: '층·재료가 결합된 부품 단품' },
  { what: '값', material: '측정값', composite: '추정값 — 어느 역공학에서, 무엇을 가정하고' },
  {
    what: '정체성',
    material: '재료 → 시료 → 시편 → 시험',
    composite: '부품 → 구성체 → 변형체(무엇이 다른가) → 로트 → 시편 → 시험',
  },
  { what: '시험', material: '확립된 규격', composite: '시험법 자체가 개발 대상 — 초안 → 검증 → 규격' },
  { what: '결과', material: '물성 카드', composite: '재현 판정 · 층별 추정 물성 · 판별' },
  { what: '시뮬레이션', material: '물성을 입력으로', composite: '방법론이 산출물 — 시험법과 규격 쌍' },
]

/** 한 줄로 이어져야 하는 네 사슬. 기존 시험 데이터 체계와 정렬되어야 한다. */
const CHAIN = [
  { step: '기존 부품 시험 데이터', how: '현행 관리 방식 그대로 수용' },
  { step: '재현 시험 (시장 불량)', how: '시험법·불량 모드·재현 판정을 구조화' },
  { step: '역공학·추정 물성', how: '가정·불확실성과 함께 기록' },
  { step: '시뮬레이션 방법론', how: '시나리오를 시험과 해석이 공유' },
]

const PHASES = ['1단계', '2단계', '3단계']

export default function CompositeOverviewPage() {
  const groups = realmGroups('composite').filter((group) => group.title)
  const screens = groups.flatMap((group) =>
    group.items.map((item) => ({ ...item, group: group.title ?? '' }))
  )
  const done = screens.filter((one) => !one.pending).length

  return (
    <div className="max-w-5xl space-y-8">
      <PageHeader
        title="복합 물성"
        description="여러 층·재료가 결합된 부품 단품의 거동 — 복합체를 시험하고 역공학으로 뽑는 값, 층 하나가 바뀌었을 때의 차이, 시장 불량을 재현하는 시험법."
      />

      <div className="border-muted-foreground/30 bg-muted/40 flex items-start gap-3 rounded-md border border-dashed p-4 text-sm">
        <Construction className="text-muted-foreground mt-0.5 size-4 shrink-0" />
        <div>
          <p className="font-medium">지금은 화면 자리만 있습니다 — 설계 논의용.</p>
          <p className="text-muted-foreground mt-1">
            {screens.length}개 화면 중 {done}개 구현. 스키마는 ADR 0026 이 제안이고, MX 의 현행
            시험 데이터 체계(부품 코드·시험 종류·조건·판정·성적서)를 확인한 뒤 확정합니다. 그
            전에 만드는 화면은 짐작이라, 메뉴와 이 개요만 먼저 세웠습니다.
          </p>
        </div>
      </div>

      <section className="space-y-3">
        <h2 className="text-base font-semibold">재료 물성과 무엇이 다른가</h2>
        <p className="text-muted-foreground text-sm">
          시편 층위에서 이미 이름 규칙·필수 칸(방향)·치수 해석이 다릅니다. 한 틀에 넣으면
          구성체 시편에 「방향」 을 억지로 채우게 됩니다. 그래서 화면과 계층은 갈라서고,
          엔진(파일 읽기·곡선·처리·카드·기준정보·권한)만 공유합니다.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted-foreground border-b text-left text-xs">
                <th className="py-1.5 pr-3 font-medium"> </th>
                <th className="py-1.5 pr-3 font-medium">재료 물성</th>
                <th className="py-1.5 font-medium">복합 물성</th>
              </tr>
            </thead>
            <tbody>
              {CONTRAST.map((row) => (
                <tr key={row.what} className="border-b last:border-0">
                  <td className="py-1.5 pr-3 font-medium whitespace-nowrap">{row.what}</td>
                  <td className="text-muted-foreground py-1.5 pr-3">{row.material}</td>
                  <td className="py-1.5">{row.composite}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-semibold">한 줄로 이어져야 하는 네 사슬</h2>
        <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {CHAIN.map((one, index) => (
            <li key={one.step} className="rounded-md border p-3 text-sm">
              <p className="font-medium">
                <span className="text-muted-foreground mr-1 font-mono text-xs">{index + 1}</span>
                {one.step}
              </p>
              <p className="text-muted-foreground mt-1 text-xs">{one.how}</p>
            </li>
          ))}
        </ol>
        <p className="text-muted-foreground text-xs">
          식별자는 기존 시스템(PLM·트랜스·성적서)과 같아야 하고, 등급·출처 체계는 하나여야
          하며, 원본(장비 파일·사진·성적서)은 그대로 보존합니다.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-semibold">화면 — 어느 단계에 무엇이 오는가</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {PHASES.map((phase) => {
            const mine = screens.filter((one) => one.phase === phase)
            return (
              <div key={phase} className="rounded-md border">
                <div className="bg-muted/60 border-b px-3 py-2 text-sm font-medium">
                  {phase}
                  <span className="text-muted-foreground ml-2 text-xs font-normal">
                    {mine.length}개
                  </span>
                </div>
                <ul className="divide-y">
                  {mine.length === 0 && (
                    <li className="text-muted-foreground px-3 py-2 text-xs">
                      화면이 아니라 연계입니다 — SSO·BDC 이관·온톨로지·MCP.
                    </li>
                  )}
                  {mine.map((one) => (
                    <li key={one.label} className="px-3 py-2">
                      <Link
                        to={one.to ?? '#'}
                        className="hover:text-foreground flex items-center gap-2 text-sm"
                      >
                        <one.icon className="text-muted-foreground size-4 shrink-0" />
                        <span className="font-medium">{one.label}</span>
                        <span className="text-muted-foreground text-xs">{one.group}</span>
                        {one.pending && (
                          <Badge variant="outline" className="ml-auto text-[10px]">
                            미구현
                          </Badge>
                        )}
                      </Link>
                      {one.summary && (
                        <p className="text-muted-foreground mt-0.5 pl-6 text-xs">{one.summary}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold">화면을 만들기 전에 확인할 것</h2>
        <p className="text-muted-foreground text-sm">
          플랫폼을 만드는 쪽은 MX 의 시험 현장과 데이터를 직접 볼 수 없습니다. 부품 시험이
          지금 어떤 항목으로, 어디에, 어떤 규칙으로 관리되는지 — 그 답이 오면 구성체·시험법·
          판정의 스키마가 확정되거나 고쳐집니다. 요청 목록은 「플랫폼-요구사항-MX확인요청」
          문서에, 스키마 초안은 ADR 0026 에 있습니다.
        </p>
        <Link
          to="/guide"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
        >
          가이드에서 보기 <ArrowRight className="size-3.5" />
        </Link>
      </section>
    </div>
  )
}
