/**
 * 한 번만 보여 주는 비밀 값(임시 비밀번호·PAT).
 *
 * SMTP 가 없어 메일로 보낼 수 없으므로, 관리자가 이 화면에서 읽어 구두·메신저로
 * 전달한다. **다시 볼 수 없다는 것**을 분명히 말해 주지 않으면 창을 닫고 나서
 * 다시 찾게 되고, 결국 비밀번호를 또 재설정하게 된다.
 */

import { useState } from 'react'
import { Check, Copy, KeyRound } from 'lucide-react'

import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'

interface SecretOnceDialogProps {
  open: boolean
  onClose: () => void
  title: string
  description: string
  secret: string
  subject?: string
}

export function SecretOnceDialog({
  open,
  onClose,
  title,
  description,
  secret,
  subject,
}: SecretOnceDialogProps) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(secret)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // 클립보드 권한이 없을 수 있다. 값은 화면에 보이므로 손으로 옮기면 된다.
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="size-4" />
            {title}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {subject && (
          <p className="text-muted-foreground text-sm">
            대상: <span className="text-foreground font-medium">{subject}</span>
          </p>
        )}

        <div className="flex items-center gap-2">
          <code className="bg-muted min-w-0 flex-1 truncate rounded-md px-3 py-2 font-mono text-sm">
            {secret}
          </code>
          <Button variant="outline" size="icon" onClick={copy} aria-label="복사">
            {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
          </Button>
        </div>

        <p className="text-muted-foreground text-xs">
          이 값은 다시 표시되지 않습니다. 창을 닫기 전에 전달하세요. 받는 사람은 첫 로그인 시
          비밀번호를 바꿔야 합니다.
        </p>

        <DialogFooter>
          <Button onClick={onClose}>전달했습니다</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
