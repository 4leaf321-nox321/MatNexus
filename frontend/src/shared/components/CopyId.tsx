/**
 * 식별자 복사 — **사람이 손으로 옮겨 적지 않게.**
 *
 * UUID 를 눈으로 읽고 다른 프로그램(MatPylon 마법사)에 치게 하면 한 글자가 틀리고,
 * 틀린 채로 「부서를 찾을 수 없습니다」 를 본다. 복사 단추 하나면 그 일이 없다.
 */

import { Check, Copy } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/shared/components/ui/button'
import { copyText } from '@/shared/lib/clipboard'

export function CopyId({ value, label = 'ID' }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    if (await copyText(value)) {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }
  }

  return (
    <span className="inline-flex items-center gap-1">
      <code className="text-muted-foreground font-mono text-xs">{value}</code>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="h-6 px-1.5"
        aria-label={`${label} 복사`}
        title={`${label} 복사`}
        onClick={copy}
      >
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </Button>
    </span>
  )
}
