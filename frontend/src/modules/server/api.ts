/** 서버 현황 — 읽기 전용. 여기서 서버를 만지는 길은 없다. */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type ServerInfo = components['schemas']['ServerInfoOut']
export type Disk = components['schemas']['DiskOut']

export const serverApi = {
  info: () => api.get<ServerInfo>('/server/info'),
}
