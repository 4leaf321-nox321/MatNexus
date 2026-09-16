# 기준선 20260916T135743Z · 9891565

| 항목 | 값 |
| --- | --- |
| 물음 | 8 (지난번 30) |
| 통과 | 6 (지난번 22) |
| 도구 호출(합) | 42 (지난번 127) |
| 물음당 호출 | 5.25 (지난번 4.23) |
| 빈손 호출 | 0 (지난번 0) |
| 지도부터 본 물음 | 6 (지난번 15) |
| 오류 | 0 (지난번 0) |
| 걸린 시간(s) | 340.2 (지난번 1129.6) |
| 비용(USD) | 3.5227 (지난번 12.1051) |

| 갈래 | 통과/전체 | 호출 | 빈손 | 지도부터 |
| --- | --- | --- | --- | --- |
| 카드 | 1/2 | 13 | 0 | 2 |
| 값 찾기 | 1/1 | 4 | 0 | 1 |
| 커버리지 | 1/2 | 8 | 0 | 1 |
| 이름 해소 | 1/1 | 2 | 0 | 0 |
| 판단 | 2/2 | 15 | 0 | 2 |

| 물음 | 결과 | 호출 | 자취 | 빠진 말 |
| --- | --- | --- | --- | --- |
| deck-02 | 미달 | 4 | search_materials → get_guide → deck_readiness → build_deck | 7 |
| deck-05 | 통과 | 9 | get_card → get_guide → search_all → deck_readiness → list_cards → get_card → get_card → render_card_deck → check_card_deck |  |
| search-04 | 통과 | 4 | resolve_property → get_guide → find_by_property → find_by_property |  |
| coverage-01 | 통과 | 3 | search_catalog → search_all → property_coverage |  |
| coverage-02 | 미달 — 기대 도구 안 씀 | 5 | get_guide → search_all → get_material → list_test_runs → list_specimens |  |
| name-03 | 통과 | 2 | resolve_property → resolve_property |  |
| judge-02 | 통과 | 6 | get_guide → search_catalog → resolve_property → search_materials → get_catalog_material → adopt_catalog_values |  |
| judge-03 | 통과 | 9 | get_guide → search_materials → deck_readiness → list_cards → property_coverage → list_test_runs → preview_card_fit → list_recipes → get_test_run |  |
