# 기준선 20261115T014428Z · 8107257

| 항목 | 값 |
| --- | --- |
| 물음 | 43 (지난번 5) |
| 통과 | 39 (지난번 5) |
| 도구 호출(합) | 227 (지난번 16) |
| 물음당 호출 | 5.28 (지난번 3.2) |
| 빈손 호출 | 0 (지난번 0) |
| 지도부터 본 물음 | 20 (지난번 1) |
| 오류 | 0 (지난번 0) |
| 걸린 시간(s) | 1491.3 (지난번 110.6) |
| 비용(USD) | 19.6643 (지난번 1.8354) |

| 갈래 | 통과/전체 | 호출 | 빈손 | 지도부터 |
| --- | --- | --- | --- | --- |
| 카드 | 10/10 | 33 | 0 | 6 |
| 값 찾기 | 8/8 | 24 | 0 | 2 |
| 커버리지 | 3/3 | 10 | 0 | 1 |
| 관계 | 5/6 | 102 | 0 | 2 |
| 이름 해소 | 2/3 | 10 | 0 | 1 |
| 판단 | 5/5 | 20 | 0 | 3 |
| 통계 | 0/1 | 6 | 0 | 1 |
| 계산식 | 1/1 | 2 | 0 | 0 |
| 점탄성 | 2/2 | 7 | 0 | 1 |
| 쓰기 멈춤 | 2/3 | 9 | 0 | 2 |
| 단위 | 1/1 | 4 | 0 | 1 |

| 물음 | 결과 | 호출 | 자취 | 빠진 말 |
| --- | --- | --- | --- | --- |
| deck-01 | 통과 | 4 | deck_readiness → list_cards → list_cards → check_card_deck |  |
| deck-02 | 통과 | 4 | search_materials → get_guide → deck_readiness → build_deck |  |
| deck-03 | 통과 | 6 | get_guide → search_materials → search_materials → deck_readiness → deck_readiness → build_deck |  |
| deck-04 | 통과 | 3 | search_materials → deck_readiness → list_test_runs |  |
| deck-05 | 통과 | 6 | get_guide → get_card → deck_readiness → get_card → build_deck → check_card_deck |  |
| deck-06 | 통과 | 4 | get_guide → deck_readiness → list_test_runs → get_material |  |
| search-01 | 통과 | 4 | resolve_property → find_by_property → find_by_property → find_by_property |  |
| search-02 | 통과 | 5 | get_guide → resolve_property → find_by_property → find_by_property → find_by_property |  |
| search-03 | 통과 | 2 | resolve_property → find_by_property |  |
| search-04 | 통과 | 2 | resolve_property → find_by_property |  |
| search-05 | 통과 | 2 | resolve_property → find_by_property |  |
| search-06 | 통과 | 4 | search_catalog → resolve_property → get_catalog_material → get_catalog_material |  |
| search-07 | 통과 | 4 | get_guide → find_by_property → list_property_items → find_by_property |  |
| search-08 | 통과 | 1 | get_material |  |
| coverage-01 | 통과 | 2 | search_materials → property_coverage |  |
| coverage-02 | 통과 | 5 | property_coverage → get_statistics → get_material → get_statistics → get_catalog_material |  |
| coverage-03 | 통과 | 3 | search_materials → get_guide → deck_readiness |  |
| graph-01 | 미달 — 호출 초과 | 90 | list_recipes → list_test_runs → list_processing_results → list_test_runs → list_test_runs → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_processing_results → list_test_runs | 건·개·결과 |
| graph-02 | 통과 | 6 | get_ontology → search_materials → list_test_runs → get_test_run → find_path → get_sample |  |
| graph-03 | 통과 | 2 | resolve_property → how_to_measure |  |
| graph-04 | 통과 | 2 | list_commissions → get_commission |  |
| graph-05 | 통과 | 1 | get_ontology |  |
| graph-06 | 통과 | 1 | get_material |  |
| name-01 | 미달 — 호출 초과 | 4 | resolve_property → find_by_property → find_by_property → find_by_property |  |
| name-02 | 통과 | 4 | resolve_property → resolve_property → resolve_property → resolve_property |  |
| name-03 | 통과 | 2 | resolve_property → get_guide |  |
| judge-01 | 통과 | 5 | list_unit_systems → get_card → get_card → convert_unit → convert_unit |  |
| judge-02 | 통과 | 6 | get_guide → search_catalog → search_materials → resolve_property → get_catalog_material → property_coverage |  |
| judge-03 | 통과 | 5 | get_guide → list_cards → search_all → deck_readiness → preview_card_fit |  |
| judge-04 | 통과 | 2 | get_guide → search_all |  |
| judge-05 | 통과 | 2 | convert_unit → convert_unit |  |
| stats-01 | 미달 — 호출 초과 | 6 | get_guide → search_materials → get_statistics → get_statistics → get_distribution → convert_unit |  |
| formula-01 | 통과 | 2 | list_formulas → list_formulas |  |
| visco-01 | 통과 | 2 | get_master_curves → get_prony_fits |  |
| card-07 | 통과 | 2 | get_guide → get_card |  |
| card-08 | 통과 | 2 | get_guide → get_card |  |
| write-01 | 통과 | 3 | get_guide → get_card → set_card_status |  |
| write-02 | 통과 | 3 | list_processing_results → get_guide → adopt_results |  |
| write-03 | 미달 — 금지 도구: mcp__matnexus__add_card_remark | 3 | get_card → add_card_remark → add_card_remark |  |
| visco-02 | 통과 | 5 | get_guide → get_master_curves → get_test_run → list_test_runs → get_master_curves |  |
| card-09 | 통과 | 1 | list_cards |  |
| card-10 | 통과 | 1 | list_cards |  |
| unit-01 | 통과 | 4 | get_guide → search_materials → get_statistics → convert_unit |  |
