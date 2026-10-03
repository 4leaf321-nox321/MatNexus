---
name: MatNexus 물성
description: MatNexus(사내 재료 물성 플랫폼)로 재료 · 시험 · 문헌 물성 · 물성 카드 · 해석 덱을 다룰 때 사용. 찾기("SUS304 항복강도"·"이 재료 시험 결과"·"200 MPa 근처 재료"), 측정법("이 물성 어떻게 재?"), 카드 · LS-DYNA 덱 만들기, 문헌 값 받아 오기, 측정 의뢰까지 — matnexus MCP 도구(HWAX 포털 게이트웨이 경유 포함)를 쓰는 모든 작업에 적용. 도구가 90개가 넘어 무엇을 쓸지는 get_guide() 가 말한다.
allowed-tools: mcp__matnexus__*,
  mcp__hwax__get_guide, mcp__hwax__matnexus_get_guide,
  mcp__hwax__search_materials, mcp__hwax__matnexus_search_materials,
  mcp__hwax__get_material, mcp__hwax__matnexus_get_material,
  mcp__hwax__convert_unit, mcp__hwax__matnexus_convert_unit,
  mcp__hwax__list_condition_fields, mcp__hwax__matnexus_list_condition_fields,
  mcp__hwax__list_unit_systems, mcp__hwax__matnexus_list_unit_systems,
  mcp__hwax__search_catalog, mcp__hwax__matnexus_search_catalog,
  mcp__hwax__get_catalog_material, mcp__hwax__matnexus_get_catalog_material,
  mcp__hwax__list_equipment, mcp__hwax__matnexus_list_equipment,
  mcp__hwax__how_to_measure, mcp__hwax__matnexus_how_to_measure,
  mcp__hwax__list_test_runs, mcp__hwax__matnexus_list_test_runs,
  mcp__hwax__get_statistics, mcp__hwax__matnexus_get_statistics,
  mcp__hwax__get_distribution, mcp__hwax__matnexus_get_distribution,
  mcp__hwax__spec_gap, mcp__hwax__matnexus_spec_gap,
  mcp__hwax__spread_by_group, mcp__hwax__matnexus_spread_by_group,
  mcp__hwax__compare_material_statistics, mcp__hwax__matnexus_compare_material_statistics,
  mcp__hwax__list_samples, mcp__hwax__matnexus_list_samples,
  mcp__hwax__get_sample, mcp__hwax__matnexus_get_sample,
  mcp__hwax__get_specimen, mcp__hwax__matnexus_get_specimen,
  mcp__hwax__list_specimens, mcp__hwax__matnexus_list_specimens,
  mcp__hwax__create_material, mcp__hwax__matnexus_create_material,
  mcp__hwax__create_sample, mcp__hwax__matnexus_create_sample,
  mcp__hwax__create_specimen, mcp__hwax__matnexus_create_specimen,
  mcp__hwax__get_test_run, mcp__hwax__matnexus_get_test_run,
  mcp__hwax__get_card, mcp__hwax__matnexus_get_card,
  mcp__hwax__match_bom, mcp__hwax__matnexus_match_bom,
  mcp__hwax__property_coverage, mcp__hwax__matnexus_property_coverage,
  mcp__hwax__deck_readiness, mcp__hwax__matnexus_deck_readiness,
  mcp__hwax__build_deck, mcp__hwax__matnexus_build_deck,
  mcp__hwax__adopt_catalog_values, mcp__hwax__matnexus_adopt_catalog_values,
  mcp__hwax__preview_card_fit, mcp__hwax__matnexus_preview_card_fit,
  mcp__hwax__list_groups, mcp__hwax__matnexus_list_groups,
  mcp__hwax__create_card_from_group, mcp__hwax__matnexus_create_card_from_group,
  mcp__hwax__create_viscoelastic_card, mcp__hwax__matnexus_create_viscoelastic_card,
  mcp__hwax__create_lve_card, mcp__hwax__matnexus_create_lve_card,
  mcp__hwax__create_card_from_tests, mcp__hwax__matnexus_create_card_from_tests,
  mcp__hwax__create_declared_card, mcp__hwax__matnexus_create_declared_card,
  mcp__hwax__list_property_items, mcp__hwax__matnexus_list_property_items,
  mcp__hwax__add_property_item, mcp__hwax__matnexus_add_property_item,
  mcp__hwax__link_property_item, mcp__hwax__matnexus_link_property_item,
  mcp__hwax__save_card_block, mcp__hwax__matnexus_save_card_block,
  mcp__hwax__set_declared_values, mcp__hwax__matnexus_set_declared_values,
  mcp__hwax__list_card_blocks, mcp__hwax__matnexus_list_card_blocks,
  mcp__hwax__list_cards, mcp__hwax__matnexus_list_cards,
  mcp__hwax__add_catalog_property, mcp__hwax__matnexus_add_catalog_property,
  mcp__hwax__add_catalog_material, mcp__hwax__matnexus_add_catalog_material,
  mcp__hwax__add_catalog_value, mcp__hwax__matnexus_add_catalog_value,
  mcp__hwax__deprecate_catalog_property, mcp__hwax__matnexus_deprecate_catalog_property,
  mcp__hwax__migrate_catalog_property, mcp__hwax__matnexus_migrate_catalog_property,
  mcp__hwax__delete_catalog_value, mcp__hwax__matnexus_delete_catalog_value,
  mcp__hwax__compare_catalog_materials, mcp__hwax__matnexus_compare_catalog_materials,
  mcp__hwax__measurement_gaps, mcp__hwax__matnexus_measurement_gaps,
  mcp__hwax__platform_summary, mcp__hwax__matnexus_platform_summary,
  mcp__hwax__resolve_property, mcp__hwax__matnexus_resolve_property,
  mcp__hwax__get_property_classification, mcp__hwax__matnexus_get_property_classification,
  mcp__hwax__classify_properties, mcp__hwax__matnexus_classify_properties,
  mcp__hwax__find_by_property, mcp__hwax__matnexus_find_by_property,
  mcp__hwax__run_batch_processing, mcp__hwax__matnexus_run_batch_processing,
  mcp__hwax__list_inbox, mcp__hwax__matnexus_list_inbox,
  mcp__hwax__assign_inbox_item, mcp__hwax__matnexus_assign_inbox_item,
  mcp__hwax__inspect_device_file, mcp__hwax__matnexus_inspect_device_file,
  mcp__hwax__check_format_profile, mcp__hwax__matnexus_check_format_profile,
  mcp__hwax__save_format_profile, mcp__hwax__matnexus_save_format_profile,
  mcp__hwax__scan_deck_format, mcp__hwax__matnexus_scan_deck_format,
  mcp__hwax__export_definition_grammar, mcp__hwax__matnexus_export_definition_grammar,
  mcp__hwax__list_export_profiles, mcp__hwax__matnexus_list_export_profiles,
  mcp__hwax__preview_export_profile, mcp__hwax__matnexus_preview_export_profile,
  mcp__hwax__save_export_profile, mcp__hwax__matnexus_save_export_profile,
  mcp__hwax__render_card_deck, mcp__hwax__matnexus_render_card_deck,
  mcp__hwax__check_card_deck, mcp__hwax__matnexus_check_card_deck,
  mcp__hwax__get_master_curves, mcp__hwax__matnexus_get_master_curves,
  mcp__hwax__get_prony_fits, mcp__hwax__matnexus_get_prony_fits,
  mcp__hwax__list_formulas, mcp__hwax__matnexus_list_formulas,
  mcp__hwax__formula_vocabulary, mcp__hwax__matnexus_formula_vocabulary,
  mcp__hwax__preview_formula, mcp__hwax__matnexus_preview_formula,
  mcp__hwax__draft_test_type, mcp__hwax__matnexus_draft_test_type,
  mcp__hwax__list_processing_steps, mcp__hwax__matnexus_list_processing_steps,
  mcp__hwax__list_processing_inputs, mcp__hwax__matnexus_list_processing_inputs,
  mcp__hwax__list_commissions, mcp__hwax__matnexus_list_commissions,
  mcp__hwax__get_commission, mcp__hwax__matnexus_get_commission,
  mcp__hwax__create_commission, mcp__hwax__matnexus_create_commission,
  mcp__hwax__list_recipes, mcp__hwax__matnexus_list_recipes,
  mcp__hwax__list_processing_results, mcp__hwax__matnexus_list_processing_results,
  mcp__hwax__get_result_curve, mcp__hwax__matnexus_get_result_curve,
  mcp__hwax__run_processing, mcp__hwax__matnexus_run_processing,
  mcp__hwax__save_recipe, mcp__hwax__matnexus_save_recipe,
  mcp__hwax__update_recipe, mcp__hwax__matnexus_update_recipe,
  mcp__hwax__get_parameter_sets, mcp__hwax__matnexus_get_parameter_sets,
  mcp__hwax__get_catalog_parameter_sets, mcp__hwax__matnexus_get_catalog_parameter_sets,
  mcp__hwax__adopt_parameter_set, mcp__hwax__matnexus_adopt_parameter_set,
  mcp__hwax__get_handbook_section, mcp__hwax__matnexus_get_handbook_section,
  mcp__hwax__search_all, mcp__hwax__matnexus_search_all,
  mcp__hwax__get_ontology, mcp__hwax__matnexus_get_ontology,
  mcp__hwax__related, mcp__hwax__matnexus_related,
  mcp__hwax__find_path, mcp__hwax__matnexus_find_path,
  mcp__hwax__get_taxonomy, mcp__hwax__matnexus_get_taxonomy
---

# MatNexus 물성

`matnexus` MCP 서버로 사내 재료 물성을 다룬다. 도구가 **90개가 넘는다.**

## 도구 이름 — 연결 방식에 따라 앞부분이 다르다

- MatNexus 에 **직접** 연결: `mcp__matnexus__get_guide`
- **HWAX 포털 게이트웨이**로 연결: `mcp__hwax__get_guide` — 다른 앱 도구와 이름이 겹치면
  `mcp__hwax__matnexus_get_guide` 로 보인다(겹침은 다른 앱의 가동 여부로 바뀐다).

이 파일과 안내는 이름을 짧게(`get_guide`) 적는다. 지금 보이는 쪽 이름으로 부르면 된다.

## 시작하기 전에 — `get_guide()` 를 먼저 부른다

단위 규약 · 값의 무게(tier · 합성) · 무엇을 어떤 순서로 쓰는지가 거기 있다. **서버가 최신본을
쥐고 있으므로** 이 파일이 오래돼도 안내는 항상 최신이다. 세부가 필요하면 주제를 지정한다.

## 포털 경유는 읽기 전용이다

HWAX 포털 게이트웨이로 부르면 MatNexus 는 그 사람 명의의 **읽기 전용** 토큰을 쓴다. 쓰는
도구는 미리보기(`dry_run=True`)까지만 된다 — 실제로 담아야 하면 사용자에게 MatNexus 에 직접
연결해 달라고 말한다(MatNexus 「내 계정 → 토큰」 의 「AI 도구에 등록하기」).

## 이 파일에 내용을 더 적지 마라

이 파일은 **각자 PC 에 복사된 사본**이라 서버를 올려도 갱신되지 않는다. 안내를 고쳐야 하면
저장소의 `mcp_server/guide/GUIDE.md` 를 고친다 — 모두에게 바로 반영된다.

도구를 추가하면 위 `allowed-tools` 에 게이트웨이 이름 두 개(`mcp__hwax__<도구>`,
`mcp__hwax__matnexus_<도구>`)를 더한다 — 빠지면 `backend/tests/architecture/test_mcp_skill.py`
가 잡는다.

## 최소 원칙 (가이드를 못 받았을 때만)

`get_guide()` 가 실패하면 이것만 지키고, 사용자에게 가이드를 못 받았다고 알린다.

- **도구가 주고받는 숫자는 SI 다.** 사람에게는 mm · N · tonne 으로 답하고 SI 를 괄호에 적는다 —
  환산은 `convert_unit` 에 시킨다. 직접 곱하지 않는다.
- **tier 4(추정)와 synthetic(합성) 값을 실측처럼 말하지 않는다.** 값마다 출처와 등급을 함께 말한다.
- **쓰는 도구는 미리보기부터** — 사람이 「그대로」 라고 한 뒤에 `dry_run=False` 로 다시 부른다.
- **이름을 모르면 찾기부터** — 재료 · 물성 이름을 추측하지 않는다.
