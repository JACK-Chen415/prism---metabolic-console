# `backend/app/services/intake.py` index

This file is intentionally one large module because:

- `IntakeService` is a thin facade over a single `KnowledgeService`
  dependency; most private helpers share instance state.
- Splitting into Mixins added import complexity without reuse.
- The public API surface is small (6 methods); the rest are helpers.

When editing, jump to the right section using the layout below.

## Layout

| Lines (approx) | Section |
| --- | --- |
| 1-40 | Module docstring + imports |
| 40-180 | Constants: `CATEGORY_ALIAS_MAP`, `MEAL_TYPE_HINTS`, regex patterns, text intent keywords |
| 180-345 | More constants: `GENERIC_CATEGORY_HINTS`, `FALLBACK_PRIORITY`, fallback ranking |
| 346-372 | `IntakeService.__init__` |
| 372-512 | Public: `parse_voice` |
| 513-573 | Public: `parse_text` |
| 574-616 | Public: `voice_auto_log` |
| 617-679 | Public: `parse_photo_result` |
| 680-696 | Public: `confirm` |
| 697-790 | Public: `reevaluate_confirm_item` |
| 791-884 | Private: `_candidate_from_voice_segment` |
| 885-975 | Private: `_candidate_from_photo_food` |
| 976-1036 | Private: `_candidate_from_confirm_item` |
| 1037-1155 | Private: `_meal_from_confirm_item` + estimation helpers |
| 1156-1295 | Private: text segmentation / cleaning (`_split_voice_segments`, `_clean_segment`, `_looks_like_meal_log_text`, `_extract_text_food_segments`, `_strip_text_log_prefix`, `_is_specific_food_segment`, `_infer_meal_type`, `_detect_time_hint`, `_extract_amount`, `_extract_taste_cues`, `_extract_follow_up_detail`) |
| 1296-1455 | Private: context / notes / warnings (`_should_use_context_completion`, `_merge_context_food_segment`, `_build_follow_up_estimated_notes`, `_compose_note`, `_normalize_unit`, `_parse_numeric_token`, `_resolve_category`, `_amount_multiplier`, `_match_common_food_hint`, `_compose_amount_text`, `_build_warnings`) |
| 1456-1620 | Private: session warnings, audit logging, source detail, misc utils |

Line numbers are approximate; rerun `grep -n "^    " backend/app/services/intake.py` for exact method locations.

## Public API contract

```
IntakeService.parse_voice(db, *, user, conditions, data: VoiceParseRequest)
    -> IntakeDraftSessionResponse

IntakeService.parse_text(db, *, user, conditions, data: TextParseRequest)
    -> IntakeDraftSessionResponse

IntakeService.voice_auto_log(db, *, user, conditions, data: VoiceAutoLogRequest)
    -> IntakeDraftSessionResponse  # best-effort, may emit session warning

IntakeService.parse_photo_result(db, *, user, conditions, data: PhotoParseRequest)
    -> IntakeDraftSessionResponse

IntakeService.confirm(db, *, user, request: IntakeConfirmRequest)
    -> IntakeConfirmResponse

IntakeService.reevaluate_confirm_item(db, *, user, item: IntakeConfirmItem, conditions)
    -> IntakeCandidate
```

All `parse_*` methods return a draft session that the UI displays for user
confirmation before calling `confirm` to persist meals.
