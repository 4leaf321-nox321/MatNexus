/**
 * 시편 고르기 — 재료 → 시료 → 시편 3단.
 *
 * 시험은 시편에 매달리는데, **사용자는 시편 이름을 외우고 있지 않다.** 계층을
 * 따라 좁혀 들어가야 고를 수 있다.
 *
 * 이 컴포넌트가 재료 모듈에 있는 이유: 고르는 대상이 재료 계층이다. 시험 모듈이
 * 자기 안에 재료 선택을 다시 구현하면 재료 화면과 규칙이 갈라진다(시험 모듈이
 * 시편 목록을 재료 화면에 끼워 넣는 것과 대칭이다).
 *
 * ## 여기서 만들 수도 있다
 *
 * **파일이 오는 순간이 재료·시료·시편을 처음 아는 순간이기도 하다.** 새로 받은
 * 판에서 시편을 뜬 사람이 시험을 올리려는데, 예전에는 이 화면이 *"재료 상세에서
 * 먼저 만드세요"* 라고 **사람을 내보냈다.** 일괄 등록에는 이미 새 시료·새 시편이
 * 있었으므로, **한 건 올릴 때가 오히려 불편했다** — 흔한 쪽이 불편한 셈이었다.
 *
 * 폼은 재료 화면의 것을 **그대로 쓴다**(`NewMaterialDialog`·`NewSampleDialog`·
 * `NewSpecimenDialog`). 두 벌로 두면 한쪽에만 칸이 늘거나 규칙이 갈린다.
 */

import { useEffect, useState } from 'react'

import { materialsApi } from '@/modules/materials/api'
import type { Material, Sample, Specimen } from '@/modules/materials/api'
import { MaterialPicker } from '@/modules/materials/MaterialPicker'
import { NewMaterialDialog } from '@/modules/materials/NewMaterialDialog'
import { NewSampleDialog } from '@/modules/materials/NewSampleDialog'
import { NewSpecimenDialog } from '@/modules/materials/NewSpecimenDialog'
import { Button } from '@/shared/components/ui/button'
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'

interface Props {
  onChange: (specimen: Specimen | null) => void
}

export function SpecimenPicker({ onChange }: Props) {
  const [picked, setPicked] = useState<Material | null>(null)
  const [samples, setSamples] = useState<Sample[]>([])
  const [specimens, setSpecimens] = useState<Specimen[]>([])
  const [materialId, setMaterialId] = useState('')
  const [sampleId, setSampleId] = useState('')
  const [making, setMaking] = useState<'material' | 'sample' | 'specimen' | null>(null)

  // 재료 목록을 미리 받아 두지 않는다. **재료는 수천 개가 된다** — 앞 200개를
  // 받아 뿌리던 예전 방식은 그때 무너지고, 뒤엣것은 없는 재료처럼 보였다.
  // 검색은 `MaterialPicker` 가 서버에 물어서 한다.

  useEffect(() => {
    setSampleId('')
    setSpecimens([])
    onChange(null)
    if (!materialId) {
      setSamples([])
      return
    }
    materialsApi
      .samples(materialId)
      .then((rows) => {
        setSamples(rows)
        if (rows.length === 1) setSampleId(rows[0].id)
      })
      .catch(() => setSamples([]))
    // onChange 는 호출부에서 매번 새로 만들 수 있어 의존성에 넣지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [materialId])

  useEffect(() => {
    onChange(null)
    if (!sampleId) {
      setSpecimens([])
      return
    }
    materialsApi
      .specimens(sampleId)
      .then((rows) => {
        setSpecimens(rows)
        if (rows.length === 1) onChange(rows[0])
      })
      .catch(() => setSpecimens([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sampleId])

  return (
    <div className="grid grid-cols-3 gap-2">
      <div className="space-y-1">
        <Label className="text-muted-foreground text-xs">재료</Label>
        {/* **검색이 붙은 것으로 바꿨다.** 예전에는 앞 200개를 그냥 목록에 뿌렸는데,
            재료가 그보다 많아지는 순간 뒤엣것은 *없는 재료처럼* 보였다. 잘렸다는
            표시도 없어서 사람이 알 방법이 없다. */}
        <MaterialPicker
          className="h-9 w-full"
          value={picked}
          placeholder="고르세요"
          onSelect={(material) => {
            setPicked(material)
            setMaterialId(material.id)
          }}
        />
        <Adder label="새 재료" onClick={() => setMaking('material')} />
      </div>

      <div className="space-y-1">
        <Label className="text-muted-foreground text-xs">시료</Label>
        <Select value={sampleId} onValueChange={setSampleId} disabled={samples.length === 0}>
          <SelectTrigger>
            <SelectValue placeholder={materialId ? '고르세요' : '재료 먼저'} />
          </SelectTrigger>
          <SelectContent>
            {samples.map((sample) => (
              <SelectItem key={sample.id} value={sample.id}>
                {String(sample.seq_no).padStart(2, '0')}
                {sample.lot_no ? ` · ${sample.lot_no}` : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Adder
          label="새 시료"
          disabled={!materialId}
          why="재료를 먼저 고르세요"
          onClick={() => setMaking('sample')}
        />
      </div>

      <div className="space-y-1">
        <Label className="text-muted-foreground text-xs">시편</Label>
        <Select
          value=""
          onValueChange={(id) => onChange(specimens.find((s) => s.id === id) ?? null)}
          disabled={specimens.length === 0}
        >
          <SelectTrigger>
            <SelectValue placeholder={sampleId ? '고르세요' : '시료 먼저'} />
          </SelectTrigger>
          <SelectContent>
            {specimens.map((specimen) => (
              <SelectItem key={specimen.id} value={specimen.id}>
                {specimen.orientation} {String(specimen.seq_no).padStart(2, '0')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Adder
          label="새 시편"
          disabled={!sampleId}
          why="시료를 먼저 고르세요"
          onClick={() => setMaking('specimen')}
        />
      </div>

      {/* **여기서 만들 수 있다고 말한다.** 예전에는 "재료 상세에서 먼저 만드세요"
          라고 다른 화면으로 보냈다 — 파일을 들고 온 사람에게 왕복을 시키는 것이다. */}
      {materialId && samples.length === 0 && (
        <p className="text-muted-foreground col-span-3 text-xs">
          이 재료에 시료가 없습니다. <b>새 시료</b> 로 여기서 만드세요.
        </p>
      )}
      {sampleId && specimens.length === 0 && (
        <p className="text-muted-foreground col-span-3 text-xs">
          이 시료에 시편이 없습니다. <b>새 시편</b> 으로 여기서 만드세요.
        </p>
      )}

      {/* 만든 것을 **곧바로 고른다.** 목록을 다시 받아 찾게 하면 방금 만든 것이
          안 보이는 순간이 생기고, 사용자는 실패한 줄 안다. */}
      <NewMaterialDialog
        open={making === 'material'}
        onClose={() => setMaking(null)}
        onDone={(material) => {
          setMaking(null)
          setPicked(material)
          setMaterialId(material.id)
        }}
      />
      <NewSampleDialog
        materialId={materialId || null}
        open={making === 'sample'}
        onClose={() => setMaking(null)}
        onCreated={(sample) => {
          setMaking(null)
          setSamples((current) => [...current, sample])
          setSampleId(sample.id)
        }}
      />
      <NewSpecimenDialog
        sampleId={sampleId}
        open={making === 'specimen'}
        onClose={() => setMaking(null)}
        onDone={(specimen) => {
          setMaking(null)
          setSpecimens((current) => [...current, specimen])
          onChange(specimen)
        }}
      />
    </div>
  )
}

/** 칸 아래 붙는 「+ 새…」. **왜 잠겼는지 말한다** — 그냥 흐리기만 하면 고장으로 보인다. */
function Adder({
  label,
  onClick,
  disabled = false,
  why,
}: {
  label: string
  onClick: () => void
  disabled?: boolean
  why?: string
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant="ghost"
      className="text-muted-foreground h-6 px-1 text-xs"
      disabled={disabled}
      title={disabled ? why : undefined}
      onClick={onClick}
    >
      + {label}
    </Button>
  )
}
