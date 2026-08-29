/**
 * 단위 현황 — **무엇을 받아 무엇으로 저장하고 무엇으로 보여 주는가.**
 *
 * 40개 단위와 15개 차원이 코드 안에만 있어서, "우리 시스템이 kgf 를 받나",
 * "온도를 뭘로 저장하나" 를 답하려면 소스를 열어야 했다.
 *
 * ## 왜 고칠 수 없게 두는가
 *
 * 이 화면은 **읽기 전용이다.** 관리 화면이 있으면 대개 고칠 수 있어야 할 것
 * 같지만, 여기는 반대다.
 *
 * **환산 계수는 이미 저장된 숫자의 뜻이다.** `mm` 을 0.001 에서 0.01 로 고치면
 * 어제 저장한 3.5(=3.5mm) 와 오늘 저장한 3.5(=35mm) 가 DB 에서 구분되지 않는다.
 * 되돌릴 방법이 없고, 틀렸다는 것을 알아챌 방법도 없다 — 숫자는 여전히
 * 그럴듯하다. 이 프로젝트가 가장 비싸게 겪는 결함이 정확히 그 계열이다.
 *
 * **저장 단위(SI)도 마찬가지다.** 응력의 저장 단위를 Pa 에서 MPa 로 바꾸면 그
 * 순간 기존 곡선 전부가 10⁶ 배 틀린 값이 된다.
 *
 * 그래서 이 둘은 코드에 두고 테스트가 지킨다. 바꾸려면 배포가 필요하고,
 * **그게 맞다** — 이 표를 바꾸는 것은 기능 추가가 아니라 데이터 해석의 변경이다.
 *
 * ## 그럼 무엇이 설정 대상인가
 *
 * **화면 표시 단위**뿐이다. 저장은 Pa 로 두고 화면에만 kgf/mm² 를 쓰는 것은
 * 안전하다 — 잘못 잡아도 보이는 숫자만 이상하고 저장된 값은 그대로다. 부서마다
 * 따르는 규격이 다르므로 언젠가 필요해진다. 지금은 코드에 있고(`units.ts`),
 * 요구가 생기면 부서 설정으로 옮긴다.
 */

import { Lock } from 'lucide-react'

import { display } from '@/shared/units'
import { unitsApi } from '@/modules/units/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'

/**
 * 긴 배수를 짧게. `6894.757293168` 은 아무도 안 읽는다.
 *
 * **자릿수를 버리지는 않는다** — 정확한 값은 마우스를 올리면 나온다. 여기서는
 * 자릿수 감각만 준다.
 */
function compact(text: string): string {
  const value = Number(text)
  if (!Number.isFinite(value) || value === 0) return text
  const magnitude = Math.abs(value)
  if (magnitude >= 1000 || magnitude < 0.01) {
    const exponent = Math.floor(Math.log10(magnitude))
    const mantissa = value / 10 ** exponent
    const head = Number(mantissa.toPrecision(3))
    return head === 1 ? `10^${exponent}` : `${head}×10^${exponent}`
  }
  return String(Number(value.toPrecision(4)))
}

/** 사람이 읽는 차원 이름. 없으면 원문을 그대로 보여 준다. */
const DIMENSION_LABEL: Record<string, string> = {
  angle: '각도',
  angular_frequency: '각주파수',
  compliance: '컴플라이언스',
  density: '밀도',
  dimensionless: '무차원',
  force: '하중',
  frequency: '주파수',
  inverse_temperature: '역온도',
  length: '길이',
  mass: '질량',
  strain: '변형률',
  strain_rate: '변형률속도',
  stress: '응력',
  temperature: '온도',
  time: '시간',
  velocity: '속도',
}

/**
 * 표만. **머리글이 없다** — 기준정보 화면이 자기 머리글 아래 한 칸으로 품는다.
 *
 * 단위는 사람이 폼에서 고르는 목록이라는 점에서 기준정보와 같은 것이다. 다만
 * **고칠 수 없다는 점이 다르고**, 그래서 축 목록에서도 따로 떨어뜨려 세운다.
 */
export function UnitsContent() {
  const units = useResource(() => unitsApi.list(), [])
  const rows = units.data?.dimensions ?? []

  return (
    <div>
      <ErrorNotice error={units.error} className="mb-4" />

      {/* **고칠 수 없다는 것을 먼저 말한다.** 관리 화면인데 버튼이 없으면 사람은
          자기 권한을 의심한다. 못 고치는 것이 의도이고 이유가 있다. */}
      <div className="mb-4 flex gap-2 rounded-md border p-3 text-xs">
        <Lock className="mt-0.5 size-4 shrink-0" />
        <div>
          <p>
            <b>이 표는 화면에서 고칠 수 없습니다.</b> 환산 계수는 이미 저장된 숫자의
            뜻입니다 — <code>mm</code> 을 0.001 에서 0.01 로 바꾸면 어제 저장한
            3.5(=3.5mm)와 오늘 저장한 3.5(=35mm)가 DB 에서 구분되지 않습니다.
            되돌릴 수도, 틀렸다는 것을 알아챌 수도 없습니다.
          </p>
          <p className="text-muted-foreground mt-1">
            바꾸려면 코드를 고치고 배포해야 하며, 그게 맞습니다 — 이 표를 바꾸는
            것은 기능 추가가 아니라 <b>데이터 해석의 변경</b>입니다.{' '}
            <b>화면 표시 단위</b>(저장은 Pa, 화면은 MPa)는 성격이 달라 나중에 부서
            설정으로 열 수 있습니다.
          </p>
        </div>
      </div>

      {units.data && (
        <p className="text-muted-foreground mb-2 text-xs">
          {rows.length}개 차원 · {units.data.total_units}개 표기
        </p>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>차원</TableHead>
            <TableHead>저장</TableHead>
            <TableHead>화면</TableHead>
            <TableHead>
              파일에서 알아듣는 기호
              {/* **색만으로 뜻을 나르지 않는다.** 범례를 표 아래 문단에 두었더니
                  "검은 것과 아닌 것의 차이가 뭐냐" 는 질문이 나왔다. 뜻은
                  그것을 쓰는 자리 옆에 있어야 한다. */}
              <span className="text-muted-foreground block text-xs font-normal">
                진한 것이 저장 단위 · 나머지는 저장할 때 환산
              </span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => {
            const shown = display(row.si_unit, row.dimension)
            return (
              <TableRow key={row.dimension}>
                <TableCell>
                  <div className="text-sm">
                    {DIMENSION_LABEL[row.dimension] ?? row.dimension}
                  </div>
                  <span className="text-muted-foreground font-mono text-xs">
                    {row.dimension}
                  </span>
                  {row.alias_of && (
                    <p className="text-muted-foreground mt-0.5 text-xs">
                      {/* 단위로는 못 가르고 차원으로만 갈리는 것이 있다 —
                          변형률과 tan δ 는 저장 단위가 둘 다 `1` 이다. */}
                      <b>{row.alias_of}</b> 이 이 차원의 별칭입니다 — 검증에서는 같게
                      치고, 화면에서만 다르게 보여 줍니다.
                    </p>
                  )}
                </TableCell>

                <TableCell>
                  <Badge variant="secondary" className="font-mono">
                    {row.si_unit}
                  </Badge>
                </TableCell>

                <TableCell>
                  <span className="font-mono text-sm">{shown.unit || '(그대로)'}</span>
                  {/* **방향을 적는다.** 옆 열의 배수는 반대 방향(기호→저장)이라,
                      `×` 만 있으면 두 숫자가 왜 서로 역수인지 알 수 없다. */}
                  {(shown.factor !== 1 || shown.offset !== 0) && (
                    <p className="text-muted-foreground font-mono text-xs">
                      저장×{compact(String(shown.factor))}
                      {shown.offset !== 0 &&
                        ` ${shown.offset > 0 ? '+' : '−'} ${Math.abs(shown.offset)}`}
                    </p>
                  )}
                </TableCell>

                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {row.units.map((unit) => (
                      <Badge
                        key={unit.symbol}
                        variant={unit.is_si ? 'default' : 'outline'}
                        className="font-mono text-xs"
                        title={
                          unit.is_si
                            ? '저장 단위 — 이 차원의 값은 언제나 이것으로 저장됩니다.'
                            : unit.offset === '0'
                              ? `1 ${unit.symbol} = ${unit.factor} ${row.si_unit}`
                              : `${row.si_unit} = 값 × ${unit.factor} + ${unit.offset}`
                        }
                      >
                        {unit.symbol}
                        {/* 마우스를 올려야 아는 것은 없는 것과 비슷하다. **관계식으로
                            적는다** — `×10^6` 만 있으면 어느 쪽으로 곱하는지 모른다. */}
                        {!unit.is_si && unit.factor !== '1' && (
                          <span className="opacity-60">
                            ={compact(unit.factor)}
                            {row.si_unit}
                          </span>
                        )}
                      </Badge>
                    ))}
                  </div>
                  {/* **장비마다 같은 단위를 다르게 적는다.** 정본만 보여 주면
                      "우리 장비는 N/mm2 로 적는데 되나" 를 여전히 코드로 확인해야
                      한다. 마이크로 기호(U+00B5)와 그리스 뮤(U+03BC)처럼 눈으로는
                      구분이 안 되는 것도 있다. */}
                  {row.aliases.length > 0 && (
                    <p className="text-muted-foreground mt-1 font-mono text-xs">
                      {row.aliases.map((alias) => `${alias.written}→${alias.means}`).join('  ')}
                    </p>
                  )}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>

      <div className="text-muted-foreground mt-4 space-y-2 text-xs">
        <p>
          <b>알아듣는 기호</b>는 장비가 값 옆에 적어 보내는 단위 글자입니다 — Zwick
          은 <code>"Specimen thickness a0", 0.986, "mm"</code> 처럼 적습니다. 그
          글자를 알아들어야 SI 로 바꿔 저장할 수 있습니다. 입력 폼도 같은 것을
          씁니다. <code>→</code> 는 다른 표기를 무엇으로 읽는지입니다. 대소문자는
          가리지 않지만,{' '}
          <b>대소문자만 다른 두 단위가 있으면 정확히 써야 합니다</b> — 예를 들어{' '}
          <code>mm</code> 과 <code>Mm</code> 처럼 뜻이 갈리는 쌍은 추측하지 않고
          거절합니다.
        </p>
        <p>
          여기 없는 표기가 파일에 오면 <b>조용히 넘어가지 않고 실패합니다.</b> 모르는
          단위를 1 로 치면 그 곡선은 오류 없이 엉뚱한 크기가 되고, 나중에 찾을 방법이
          없습니다.
        </p>
      </div>
    </div>
  )
}
