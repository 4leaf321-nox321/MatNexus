# 기준선 20261015T222340Z · acf0f01

| 항목 | 값 |
| --- | --- |
| 물음 | 40 (지난번 6) |
| 통과 | 36 (지난번 6) |
| 도구 호출(합) | 137 (지난번 13) |
| 물음당 호출 | 3.42 (지난번 2.17) |
| 빈손 호출 | 0 (지난번 0) |
| 지도부터 본 물음 | 19 (지난번 1) |
| 오류 | 0 (지난번 0) |
| 걸린 시간(s) | 1273.2 (지난번 140.6) |
| 비용(USD) | 15.8358 (지난번 1.8253) |

| 갈래 | 통과/전체 | 호출 | 빈손 | 지도부터 |
| --- | --- | --- | --- | --- |
| 카드 | 7/8 | 35 | 0 | 6 |
| 값 찾기 | 7/8 | 26 | 0 | 3 |
| 커버리지 | 3/3 | 9 | 0 | 1 |
| 관계 | 6/6 | 20 | 0 | 2 |
| 이름 해소 | 3/3 | 7 | 0 | 1 |
| 판단 | 4/5 | 18 | 0 | 4 |
| 통계 | 0/1 | 8 | 0 | 1 |
| 계산식 | 1/1 | 2 | 0 | 0 |
| 점탄성 | 2/2 | 5 | 0 | 0 |
| 쓰기 멈춤 | 3/3 | 7 | 0 | 1 |

| 물음 | 결과 | 호출 | 자취 | 빠진 말 |
| --- | --- | --- | --- | --- |
| deck-01 | 통과 | 3 | get_guide → deck_readiness → get_card |  |
| deck-02 | 통과 | 3 | search_materials → deck_readiness → build_deck |  |
| deck-03 | 통과 | 6 | get_guide → search_materials → search_materials → deck_readiness → deck_readiness → build_deck |  |
| deck-04 | 통과 | 4 | get_guide → search_materials → deck_readiness → list_test_runs |  |
| deck-05 | 미달 — 호출 초과 | 11 | get_guide → get_card → list_cards → get_card → get_card → get_card → check_card_deck → check_card_deck → check_card_deck → check_card_deck → build_deck |  |
| deck-06 | 통과 | 3 | search_all → get_guide → deck_readiness |  |
| search-01 | 통과 | 3 | resolve_property → find_by_property → find_by_property |  |
| search-02 | 미달 — 호출 초과 | 6 | resolve_property → get_guide → find_by_property → find_by_property → find_by_property → find_by_property |  |
| search-03 | 통과 | 2 | resolve_property → find_by_property |  |
| search-04 | 통과 | 2 | resolve_property → find_by_property |  |
| search-05 | 통과 | 2 | resolve_property → find_by_property |  |
| search-06 | 통과 | 6 | get_guide → search_catalog → resolve_property → get_catalog_material → search_all → find_by_property |  |
| search-07 | 통과 | 3 | resolve_property → find_by_property → find_by_property |  |
| search-08 | 통과 | 2 | get_guide → get_material |  |
| coverage-01 | 통과 | 1 | property_coverage |  |
| coverage-02 | 통과 | 5 | get_guide → property_coverage → get_material → get_statistics → get_statistics |  |
| coverage-03 | 통과 | 3 | search_materials → deck_readiness → property_coverage |  |
| graph-01 | 통과 | 4 | list_recipes → list_test_runs → get_guide → list_processing_results |  |
| graph-02 | 통과 | 7 | get_ontology → search_materials → list_test_runs → get_test_run → get_specimen → find_path → get_sample |  |
| graph-03 | 통과 | 4 | resolve_property → how_to_measure → list_equipment → list_equipment |  |
| graph-04 | 통과 | 2 | list_commissions → get_commission |  |
| graph-05 | 통과 | 1 | get_ontology |  |
| graph-06 | 통과 | 2 | get_material → get_catalog_material |  |
| name-01 | 통과 | 2 | resolve_property → how_to_measure |  |
| name-02 | 통과 | 3 | resolve_property → search_all → resolve_property |  |
| name-03 | 통과 | 2 | resolve_property → get_guide |  |
| judge-01 | 통과 | 5 | get_guide → list_unit_systems → search_all → deck_readiness → build_deck |  |
| judge-02 | 미달 | 1 | get_guide | 등급·tier·출처·실측 |
| judge-03 | 통과 | 7 | get_guide → search_materials → list_cards → deck_readiness → property_coverage → list_test_runs → preview_card_fit |  |
| judge-04 | 통과 | 3 | get_guide → search_all → search_catalog |  |
| judge-05 | 통과 | 2 | convert_unit → convert_unit |  |
| stats-01 | 미달 — 호출 초과 | 8 | get_guide → search_materials → get_statistics → get_distribution → convert_unit → convert_unit → convert_unit → convert_unit |  |
| formula-01 | 통과 | 2 | list_formulas → list_formulas |  |
| visco-01 | 통과 | 2 | get_master_curves → get_prony_fits |  |
| card-07 | 통과 | 2 | get_guide → get_card |  |
| card-08 | 통과 | 3 | get_card → list_cards → list_cards |  |
| write-01 | 통과 | 3 | get_guide → get_card → set_card_status |  |
| write-02 | 통과 | 2 | list_processing_results → adopt_results |  |
| write-03 | 통과 | 2 | get_card → add_card_remark |  |
| visco-02 | 통과 | 3 | search_all → get_master_curves → get_test_run |  |
