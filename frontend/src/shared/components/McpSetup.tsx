/**
 * AI 도구에 MatNexus 를 붙이는 방법 — **도구마다 붙이는 자리가 다르다.**
 *
 * 토큰을 발급받고도 「그래서 이걸 어디에 넣나」 에서 막힌다. 도구마다 파일도
 * 형식도 다르고(터미널 명령 · JSON · TOML), 그것을 사람이 문서에서 옮겨 적는
 * 동안 따옴표 하나가 어긋난다. 그래서 **완성된 것을 복사하게** 한다.
 *
 * ReportArchive 의 「AI 설정 → MCP」 탭에서 가져온 틀이다. 거기서 이미 겪은 것
 * 셋을 그대로 물려받는다:
 *
 * 1. **토큰이 없어도 형식을 보여 준다.** 「먼저 발급하세요」 만 띄우면 무엇을
 *    받게 되는지 모른 채 발급하게 된다. 자리표시자를 넣어 두고, 발급하면 그
 *    자리에 실제 토큰이 채워진다.
 * 2. **stdio 만 받는 도구가 있다.** Claude Desktop·Codex·Gemini 는 설정 파일에
 *    HTTP 서버를 못 적는다 — `npx mcp-remote` 브리지로 잇는다(Node.js 가 필요).
 *    Claude Code 는 HTTP 를 직접 받으므로 브리지 없이 붙인다.
 * 3. **헤더 값에 공백이 있다**(`Bearer mnx_pat_…`). 그대로 args 에 적으면 도구에
 *    따라 잘린다 — env 로 넣고 `${AUTH}` 로 참조한다(치환은 mcp-remote 가 한다).
 *
 * ## 주소는 짐작한다
 *
 * MCP 서버는 웹과 같은 기계에서 8012 로 도는 것이 기본이다(`mcp_server/README`).
 * 화면이 그것을 확인할 길은 없으므로 **지금 보고 있는 주소**에서 만들고, 다르면
 * 고치라고 말한다. 틀린 주소를 조용히 주는 것보다 낫다.
 */

import { useState } from 'react'

import { Button } from '@/shared/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { copyText } from '@/shared/lib/clipboard'

/** 토큰을 아직 안 받았을 때 명령에 끼워 두는 자리. */
export const TOKEN_PLACEHOLDER = '‹발급받은_토큰›'

/** MCP 서버 기본 포트(`MATNEXUS_MCP_PORT`). */
const MCP_PORT = 8012

function mcpUrl(): string {
  const host = typeof window === 'undefined' ? 'localhost' : window.location.hostname
  return `http://${host}:${MCP_PORT}/mcp`
}

function CopyBlock({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="space-y-2">
      <pre className="bg-muted overflow-x-auto rounded px-3 py-2 font-mono text-[11px] whitespace-pre">
        {text}
      </pre>
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={async () => {
          // **복사가 실패해도 「복사됨」 을 띄우지 않는다.** 사내에서 IP 로 열면
          // 클립보드 API 가 없어 조용히 안 되는 일이 있었다(`lib/clipboard`).
          if (await copyText(text)) {
            setCopied(true)
            window.setTimeout(() => setCopied(false), 1500)
          }
        }}
      >
        {copied ? '복사됨' : `${label} 복사`}
      </Button>
    </div>
  )
}

/**
 * @param token 방금 발급된 평문. 없으면 자리표시자로 형식만 보여 준다.
 */
export function McpSetup({ token }: { token?: string | null }) {
  const url = mcpUrl()
  const key = token || TOKEN_PLACEHOLDER

  // Claude Code — HTTP 를 직접 받는다. 브리지가 없으니 Node.js 도 필요 없다.
  const claudeCode = `claude mcp add --transport http matnexus ${url} --header "Authorization: Bearer ${key}"`

  // Claude Desktop — 설정 파일은 stdio(command) 서버만 받는다. `mcpServers` 중괄호
  // 안에 넣을 **항목만** 준다 — 바깥까지 주면 이미 있는 설정을 덮어쓴다.
  const bridge = {
    command: 'npx',
    args: ['-y', 'mcp-remote', url, '--allow-http', '--header', 'Authorization:${AUTH}'],
    env: { AUTH: `Bearer ${key}`, NODE_OPTIONS: '--use-system-ca' },
  }
  const desktop = `"matnexus": ${JSON.stringify(bridge, null, 2)}`

  // Codex CLI — 같은 브리지를 TOML 로.
  const codex = `[mcp_servers.matnexus]
command = "npx"
args = ["-y", "mcp-remote", "${url}", "--allow-http", "--header", "Authorization:\${AUTH}"]

[mcp_servers.matnexus.env]
AUTH = "Bearer ${key}"
NODE_OPTIONS = "--use-system-ca"`

  // Gemini CLI 의 항목 모양은 Claude Desktop 과 같다 — 같은 글을 두 벌 만들지 않는다.
  const gemini = desktop

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-xs">
        {token ? (
          <>
            방금 발급한 토큰이 아래 설정에 <strong>채워져 있습니다.</strong> 쓰는 도구를 골라
            복사하세요 — 이 값은 화면을 벗어나면 다시 못 봅니다.
          </>
        ) : (
          <>
            아래는 <strong>예시 형식</strong>입니다. 토큰 자리에{' '}
            <code className="font-mono">{TOKEN_PLACEHOLDER}</code> 가 들어가 있고, 위에서 토큰을
            발급하면 그 자리에 실제 값이 채워집니다.
          </>
        )}
      </p>

      <Tabs defaultValue="claude-code">
        <TabsList>
          <TabsTrigger value="claude-code">Claude Code</TabsTrigger>
          <TabsTrigger value="desktop">Claude Desktop</TabsTrigger>
          <TabsTrigger value="codex">Codex CLI</TabsTrigger>
          <TabsTrigger value="gemini">Gemini CLI</TabsTrigger>
        </TabsList>

        <TabsContent value="claude-code" className="space-y-2">
          <p className="text-muted-foreground text-xs">
            터미널에 그대로 붙여 넣습니다. HTTP 를 직접 받으므로 별도 프로그램이 필요 없습니다.
          </p>
          <CopyBlock text={claudeCode} label="명령" />
        </TabsContent>

        <TabsContent value="desktop" className="space-y-2">
          <p className="text-muted-foreground text-xs">
            설정 → 개발자 → 「설정 편집」으로{' '}
            <code className="font-mono">claude_desktop_config.json</code> 을 열고, 아래 항목을{' '}
            <code className="font-mono">{'"mcpServers": { }'}</code> 중괄호 <strong>안에</strong>{' '}
            붙여 넣은 뒤 다시 시작합니다. 이미 다른 항목이 있으면 사이에 쉼표를 넣으세요.
          </p>
          <CopyBlock text={desktop} label="항목" />
        </TabsContent>

        <TabsContent value="codex" className="space-y-2">
          <p className="text-muted-foreground text-xs">
            <code className="font-mono">~/.codex/config.toml</code> 에 아래를 더한 뒤 Codex 를 다시
            시작합니다.
          </p>
          <CopyBlock text={codex} label="설정" />
        </TabsContent>

        <TabsContent value="gemini" className="space-y-2">
          <p className="text-muted-foreground text-xs">
            <code className="font-mono">~/.gemini/settings.json</code> 의{' '}
            <code className="font-mono">{'"mcpServers": { }'}</code> 중괄호 <strong>안에</strong>{' '}
            붙여 넣은 뒤 다시 시작합니다.
          </p>
          <CopyBlock text={gemini} label="항목" />
        </TabsContent>
      </Tabs>

      <p className="text-muted-foreground text-xs">
        주소는 지금 보고 있는 서버(<code className="font-mono">{url}</code>)로 짐작한 것입니다 — MCP
        서버가 다른 기계나 포트에서 돌면 그 부분을 고치세요. Claude Code 를 뺀 셋은{' '}
        <strong>Node.js</strong> 가 있어야 합니다(<code className="font-mono">npx</code> 를 씁니다).
      </p>
    </div>
  )
}
