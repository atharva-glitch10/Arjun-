# Graph Report - Arjun  (2026-11-04)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 3342 nodes · 8592 edges · 131 communities (114 shown, 17 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 512 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `62f61ccb`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 71
- Community 72
- Community 73
- Community 74
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 82
- Community 83
- Community 84
- Community 85
- Community 86
- Community 87
- Community 88
- Community 89
- Community 90
- Community 91
- Community 92
- Community 93
- Community 94
- Community 95
- Community 96
- Community 97
- Community 98
- Community 99
- Community 100
- Community 101
- Community 102
- Community 103
- Community 104
- Community 105
- Community 106
- Community 107
- Community 108
- Community 109
- Community 110
- Community 111
- Community 112
- Community 113
- Community 114
- Community 115
- Community 117
- Community 120
- Community 121
- Community 122
- Community 124
- Community 125
- Community 126
- Community 128

## God Nodes (most connected - your core abstractions)
1. `TurnEngine` - 145 edges
2. `CoreClient` - 105 edges
3. `entrypoint()` - 61 edges
4. `TurnLog` - 56 edges
5. `EvonClient` - 48 edges
6. `Dashboard()` - 44 edges
7. `normalize()` - 37 edges
8. `make_engine()` - 37 edges
9. `ElderApp()` - 36 edges
10. `ask()` - 36 edges

## Surprising Connections (you probably didn't know these)
- `predict()` --uses--> `Profile`  [INFERRED]
  eval/run_eval.py → services/reasoning/reasoning_svc/parser.py
- `main()` --uses--> `EvonClient`  [INFERRED]
  eval/llm_compare.py → services/reasoning/reasoning_svc/evon.py
- `run_intents()` --uses--> `Profile`  [INFERRED]
  eval/llm_compare.py → services/reasoning/reasoning_svc/parser.py
- `_load_settings()` --references--> `LlmSettings`  [EXTRACTED]
  eval/llm_compare.py → services/reasoning/reasoning_svc/config.py
- `day_view()` --references--> `date`  [EXTRACTED]
  services/core-api/core_api/day.py → shared/schemas/intent.json

## Import Cycles
- None detected.

## Communities (131 total, 17 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (15): CoreClient, greeting(), item_text(), lang_or_default(), _part_key(), say_clock(), say_date(), say_time() (+7 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (46): run_intents(), AppCmd, clean_query(), _common_prefix(), _control(), covers(), _has(), _is() (+38 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (51): _at(), day_view(), part_of_day(), add_medicine(), delete_medicine(), dose_history(), dose_snooze(), dose_taken() (+43 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (8): _MediaChoice, _sentence(), _short_title(), TurnEngine, res(), out(), TurnResult, api()

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (29): ensure_columns(), get_db(), make_engine(), family_join(), family_name(), JoinOut, active_room(), livekit_token() (+21 more)

### Community 5 - "Community 5"
Cohesion: 0.07
Nodes (32): IdleCloser, IdlePolicy, Clock, make_closer(), get_busy(), run(), test_a_failing_busy_lookup_keeps_the_session_open(), test_after_60_quiet_seconds_it_says_the_closing_line_then_closes_in_that_order() (+24 more)

### Community 6 - "Community 6"
Cohesion: 0.10
Nodes (44): add_appointment(), add_contact(), caregiver_requests(), _check_reminder(), _complete(), complete_reminder(), confirm(), create_reminder() (+36 more)

### Community 7 - "Community 7"
Cohesion: 0.06
Nodes (40): clean_title(), parse_feed_titles(), reset_quota_for_tests(), add(), add_feed(), FakeGoogle, feeds(), fresh_state() (+32 more)

### Community 8 - "Community 8"
Cohesion: 0.14
Nodes (45): add_family(), ask(), at(), Clock, FakeLLM, hear(), make_engine(), open_checkin() (+37 more)

### Community 9 - "Community 9"
Cohesion: 0.07
Nodes (43): engine(), _fresh(), Google, household(), link(), _llm(), test_a_bare_bhajan_request_uses_the_family_playlist_without_a_search(), test_a_care_command_wins_over_a_generic_show() (+35 more)

### Community 10 - "Community 10"
Cohesion: 0.07
Nodes (19): DeliveryLoop, SessionState, Fakes, run(), test_a_claim_error_does_not_kill_the_loop(), test_a_failing_screen_update_does_not_silence_the_item(), test_a_failing_spoken_call_is_retried_and_the_loop_survives(), test_a_spoken_call_that_never_works_is_given_up_without_crashing() (+11 more)

### Community 11 - "Community 11"
Cohesion: 0.08
Nodes (42): _pending(), test_aaj_kay_aahe_now_includes_appointments_and_medicines(), test_date_query(), test_due_medicine_is_guided_by_name_and_dose_from_sql(), test_next_up_lists_pending_items_verbatim_then_next(), test_next_up_with_nothing_planned_after_dinner(), test_time_query_in_english(), test_time_query_uses_clock_and_names_what_is_next() (+34 more)

### Community 12 - "Community 12"
Cohesion: 0.05
Nodes (47): context, dockerfile, build, depends_on, environment, ports, postgres, ARJUN_ASK_BEFORE_ACTING (+39 more)

### Community 13 - "Community 13"
Cohesion: 0.09
Nodes (18): _conversation_rules(), EvonClient, load_intent_schema(), _parse_json_object(), redact(), strip_thinking(), _system_prompt(), trim_to_sentence() (+10 more)

### Community 14 - "Community 14"
Cohesion: 0.12
Nodes (43): MarkCell(), Frame(), Gallery(), MediaPreview(), noop(), BellIcon(), CalendarIcon(), CheckIcon() (+35 more)

### Community 15 - "Community 15"
Cohesion: 0.16
Nodes (25): ack(), ack_item(), AckIn, claim(), claim_delivery(), _count_try(), DeliveryOut, enqueue() (+17 more)

### Community 16 - "Community 16"
Cohesion: 0.19
Nodes (40): _all(), _at(), _by_kind(), _clock(), _deliveries(), _hear(), test_a_check_in_that_waited_hours_is_not_asked_at_all(), test_a_day_has_at_most_the_configured_number_of_questions() (+32 more)

### Community 17 - "Community 17"
Cohesion: 0.10
Nodes (27): CoreError, debug_log(), llm_debug_enabled(), briefing(), BriefingOut, delivery_next(), delivery_release(), delivery_spoken() (+19 more)

### Community 18 - "Community 18"
Cohesion: 0.14
Nodes (16): test_every_event_gets_a_larger_turn_number_so_the_app_can_tell_them_apart(), test_turnlog_records_the_action_type_and_whether_it_was_ignored(), test_an_ignored_transcript_is_logged_without_its_words(), _rows(), _say(), test_a_tapped_turn_gets_its_own_row_and_is_marked(), test_close_flushes_unanswered_turns_as_incomplete(), test_final_before_end_of_speech_still_gets_its_eos() (+8 more)

### Community 19 - "Community 19"
Cohesion: 0.12
Nodes (37): AUTO_START_COOLDOWN_MS, cardFor(), itemOf(), ON_SCREEN, RECONNECT_BACKOFF_MS, reconnectDelay(), REST_AFTER_MS, restingScreen() (+29 more)

### Community 20 - "Community 20"
Cohesion: 0.09
Nodes (23): add_reminder(), Clock, Llm, make(), reminder_status(), talking(), test_a_bare_done_word_outside_conversation_still_completes_the_only_open_reminder(), test_a_bare_ho_after_a_kept_story_is_chat_not_a_bare_ok() (+15 more)

### Community 21 - "Community 21"
Cohesion: 0.12
Nodes (22): ConjunctionHold, EndpointingPolicy, EndpointingSettings, ends_with_conjunction(), settings_from_env(), turn_detection_from_env(), FakeSpeech, run() (+14 more)

### Community 22 - "Community 22"
Cohesion: 0.09
Nodes (23): Base, Activity, AppLink, Appointment, BpReading, CaregiverRequest, Contact, Delivery (+15 more)

### Community 23 - "Community 23"
Cohesion: 0.17
Nodes (33): _all(), _clock(), _dose_id(), _fire(), _med(), _queued(), _reminder(), _spoken_medicine() (+25 more)

### Community 24 - "Community 24"
Cohesion: 0.08
Nodes (19): llm_settings(), get(), number(), LlmSettings, test_the_default_history_is_eight_exchanges(), test_a_failed_call_is_logged_too_without_text(), test_every_call_is_logged_with_provider_model_latency_and_tokens_but_no_text(), handler() (+11 more)

### Community 25 - "Community 25"
Cohesion: 0.14
Nodes (27): add_medicine(), Clock, delivered_medicine(), deliveries(), dose_history(), eng(), explode_if_called(), make_engine() (+19 more)

### Community 26 - "Community 26"
Cohesion: 0.08
Nodes (15): max_severity(), notification_severity(), RateLimitMiddleware, TokenBucket, _do(), test_a_health_complaint_is_a_watch_note_only_with_consent_once_a_day_per_kind(), test_every_notification_and_wellbeing_row_lands_in_the_feed_with_a_level(), test_middleware_answers_429_with_retry_after_and_never_limits_health() (+7 more)

### Community 27 - "Community 27"
Cohesion: 0.08
Nodes (16): Limiter, LlmBusy, split_voice_tags(), TokenBucket, _client(), _conv(), test_a_provider_429_backs_off_and_the_rules_answer(), test_companion_speech_carries_the_tag_but_the_screen_does_not() (+8 more)

### Community 28 - "Community 28"
Cohesion: 0.13
Nodes (24): BridgeReply, action_json(), attributes_for(), publish_screen(), test_ordinary_replies_clear_the_item(), test_the_action_is_published_with_the_turn_number(), test_no_action_clears_the_attribute_and_a_safety_reply_never_carries_one(), test_the_action_is_published_as_json_with_the_turn_number() (+16 more)

### Community 29 - "Community 29"
Cohesion: 0.10
Nodes (14): _fallback_url(), _fetch_feed(), http_get(), _interleave(), _max_searches_per_day(), media_status(), news(), normalise_query() (+6 more)

### Community 30 - "Community 30"
Cohesion: 0.10
Nodes (16): _local_control(), MediaMode, starts_with_wake_word(), Gate, mode(), run(), test_a_bare_control_phrase_passes(), test_a_safety_phrase_is_never_ignored() (+8 more)

### Community 31 - "Community 31"
Cohesion: 0.11
Nodes (19): claim_next_delivery(), endpointing_delay(), mark_delivery_spoken(), media_gate(), release_delivery(), session_busy(), _shared_client(), closed_attributes() (+11 more)

### Community 32 - "Community 32"
Cohesion: 0.13
Nodes (32): alarmState(), audio(), beep(), Ctx, enableAlarm(), popup(), ring(), startAlarm() (+24 more)

### Community 33 - "Community 33"
Cohesion: 0.13
Nodes (19): _card_kind(), _card_label(), day_card(), demo_enabled(), demo_fire(), DemoFireIn, enabled(), _enqueue() (+11 more)

### Community 34 - "Community 34"
Cohesion: 0.15
Nodes (23): Llm, make_engine(), _payload(), _resp(), test_a_bad_intent_name_is_rejected(), test_a_health_complaint_is_not_a_no_to_an_open_question(), test_a_long_sentence_is_not_a_no_to_an_action_that_was_already_done(), test_a_low_confidence_action_intent_is_ignored() (+15 more)

### Community 35 - "Community 35"
Cohesion: 0.09
Nodes (12): Responder, test_the_responder_tells_the_policy_the_mode_of_the_reply(), test_bridge_reads_the_spoken_line_with_tags(), test_defaults_follow_the_brief(), test_tags_go_to_timbre_v3_only(), test_thinking_marker_is_on_while_reasoning_works_and_off_after(), ask(), env_bool() (+4 more)

### Community 36 - "Community 36"
Cohesion: 0.08
Nodes (30): livekit-client, react-dom, @types/node, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react (+22 more)

### Community 37 - "Community 37"
Cohesion: 0.13
Nodes (10): Arjun, FamilyPresence, MediaState, test_a_family_participant_keeps_arjun_quiet(), test_a_locked_speech_lock_still_counts_as_quiet(), test_an_unknown_identity_leaving_does_not_clear_the_family(), test_the_elder_and_the_agent_are_not_family(), test_when_the_family_leaves_arjun_can_speak_again() (+2 more)

### Community 38 - "Community 38"
Cohesion: 0.09
Nodes (10): _GatedSse, make_tts(), prewarm(), SseTimbre, _timbre_busy(), working_tts(), warm_audio_resampler(), publish_thinking() (+2 more)

### Community 39 - "Community 39"
Cohesion: 0.13
Nodes (17): add_app_link(), AppLinkIn, AppLinkOut, AppLinkPatch, _check(), delete_app_link(), host_is_known(), host_of() (+9 more)

### Community 40 - "Community 40"
Cohesion: 0.12
Nodes (12): require_key(), testing(), Broker, feed(), feed_socket(), FeedOut, _forget(), _rows() (+4 more)

### Community 41 - "Community 41"
Cohesion: 0.14
Nodes (24): react, useAppActions(), ActionAttribute, AgentScreen, AgentState, Failure, FAILURE_TEXT, isFreshAction() (+16 more)

### Community 42 - "Community 42"
Cohesion: 0.13
Nodes (16): local_now(), _zone(), main(), tick(), today_local(), _http(), handler(), _reset() (+8 more)

### Community 43 - "Community 43"
Cohesion: 0.11
Nodes (19): sanitize_companion(), strip_filler(), strip_filler_voiced(), test_a_good_reply_passes_and_more_than_four_sentences_is_rejected(), test_missed_you_and_a_recipe_fact_are_the_prompts_job_not_the_sanitizer(), engine(), Llm, test_a_negated_pain_is_not_a_symptom() (+11 more)

### Community 44 - "Community 44"
Cohesion: 0.14
Nodes (18): issue(), join_url(), _secret(), _sign(), verify(), reset_rooms_for_tests(), _clean_rooms(), livekit() (+10 more)

### Community 45 - "Community 45"
Cohesion: 0.12
Nodes (8): FileAndCliTests, FindUrlTests, find_url(), main(), _read_env(), read_log(), wait_for_url(), _write_env()

### Community 46 - "Community 46"
Cohesion: 0.08
Nodes (15): entrypoint(), announce_closed(), claim_next(), get_busy(), _heartbeat_clear(), mark_spoken(), _on_page_attributes(), publish() (+7 more)

### Community 47 - "Community 47"
Cohesion: 0.14
Nodes (19): make(), _responder(), rows(), test_a_line_never_contains_a_secret_or_audio(), test_a_long_monologue_measures_from_the_last_end_of_speech(), test_a_reconnect_starts_above_the_previous_session(), test_a_reply_that_did_not_play_says_why(), test_a_say_that_was_interrupted_is_written_at_once_as_interrupted() (+11 more)

### Community 48 - "Community 48"
Cohesion: 0.15
Nodes (25): loadYouTubeApi(), MediaControlEvent, MediaScreen(), playerStateOf(), Window, YtApi, ArjunAction, ControlKind (+17 more)

### Community 49 - "Community 49"
Cohesion: 0.07
Nodes (26): additionalProperties, maximum, minimum, type, enum, enum, maxLength, type (+18 more)

### Community 50 - "Community 50"
Cohesion: 0.17
Nodes (16): averages(), free_port(), Judge, load_dotenv(), main(), parse_json(), post_turn(), replay_texts() (+8 more)

### Community 51 - "Community 51"
Cohesion: 0.17
Nodes (20): engine_for(), Provider, test_a_complaint_the_symptom_flow_handles_skips_the_extra_llm_call(), test_a_failed_check_without_a_failsafe_word_does_not_raise_a_false_alarm(), test_a_reply_that_mentions_a_heart_attack_with_advice_unprompted_becomes_the_doctor_line(), test_a_sample_of_every_kind_reaches_the_emergency_reply_and_never_the_llm(), test_an_llm_reply_with_cardiac_advice_to_her_cardiac_words_becomes_the_emergency_flow(), test_an_ordinary_llm_reply_is_not_touched() (+12 more)

### Community 52 - "Community 52"
Cohesion: 0.17
Nodes (19): reset_for_tests(), wait_idle(), _capture(), fake_post(), _clean(), _kinds(), _notes(), Resp (+11 more)

### Community 53 - "Community 53"
Cohesion: 0.15
Nodes (19): symptom_category(), companion_violations(), test_a_reply_over_300_characters_is_too_long(), _engine(), _kinds(), test_a_care_command_still_wins_over_a_symptom_word(), test_a_headache_gets_the_fixed_template_and_a_family_note(), test_a_story_about_the_past_fall_is_noted_but_is_not_an_emergency() (+11 more)

### Community 54 - "Community 54"
Cohesion: 0.15
Nodes (12): is_bare_control(), normalize(), should_send(), starts_with_wake_word(), strip_wake_word(), _words(), test_normal_mode_sends_everything(), test_playing_ignores_the_videos_own_audio() (+4 more)

### Community 55 - "Community 55"
Cohesion: 0.15
Nodes (6): add_bp_reading(), add_watch_sample(), latest_watch_samples(), list_bp_readings(), list_watch_samples(), _user()

### Community 56 - "Community 56"
Cohesion: 0.13
Nodes (11): lk_env(), _payload(), test_agent_name_defaults_to_arjun(), test_secret_never_appears_in_the_response(), test_token_is_short_lived(), test_token_joins_a_fresh_room_and_dispatches_arjun(), test_unconfigured_livekit_is_a_503_that_names_nothing(), test_a_numeric_string_is_accepted() (+3 more)

### Community 57 - "Community 57"
Cohesion: 0.14
Nodes (13): _family_alert(), alert_text(), claim(), configured(), _deliver(), enabled(), _post(), ready() (+5 more)

### Community 59 - "Community 59"
Cohesion: 0.12
Nodes (22): Activity, Anchor, Appointment, BpReading, call(), core(), Day, DayItem (+14 more)

### Community 60 - "Community 60"
Cohesion: 0.12
Nodes (14): main(), predict(), is_emergency(), _down_engine(), test_a_story_about_the_past_is_not_an_emergency_but_a_present_complaint_is(), test_attack_with_a_verb_is_enough_without_the_word_heart(), test_the_old_lexicon_still_works(), test_core_api_down_gives_spoken_error_not_exception() (+6 more)

### Community 61 - "Community 61"
Cohesion: 0.22
Nodes (14): add_action(), ApiError, appointment_dates(), CoreApi, display_plan(), get_seed_rows(), get_user(), load_api_key() (+6 more)

### Community 62 - "Community 62"
Cohesion: 0.16
Nodes (14): at(), build_plan(), family_contact(), first_name(), hm(), listening_interest(), PlanItem, _window_point() (+6 more)

### Community 63 - "Community 63"
Cohesion: 0.17
Nodes (7): x(), Conversation, _max(), Tracker, test_a_media_turn_counts_as_activity_and_is_recorded_with_its_title(), test_the_summary_says_what_she_watched_never_her_words(), test_conversations_flush_after_silence_into_core_api()

### Community 64 - "Community 64"
Cohesion: 0.13
Nodes (7): check_api_key_configured(), get_now(), local_now(), _zone(), lifespan(), test_empty_key_refused_outside_tests(), test_clock_uses_household_timezone_not_machine_timezone()

### Community 65 - "Community 65"
Cohesion: 0.14
Nodes (8): _confirm(), _propose(), test_caregiver_request_and_decline_gate(), test_complete_reminder_flow(), test_propose_confirm_creates_reminder_only_after_confirmation(), test_propose_missing_or_ambiguous_slots_rejected(), test_propose_reject_discards(), test_stories_private_by_default_and_shared_only_on_confirm()

### Community 66 - "Community 66"
Cohesion: 0.12
Nodes (10): test_sarvam_is_built_with_the_requested_marathi_models(), test_the_provider_defaults_to_gnani_and_only_the_word_sarvam_switches(), test_the_speaker_can_be_overridden_and_a_blank_value_keeps_the_default(), test_the_start_line_names_both_models(), test_the_turn_log_rows_say_which_services_made_them(), test_timbre_tags_never_reach_bulbul(), make_sarvam(), provider() (+2 more)

### Community 67 - "Community 67"
Cohesion: 0.16
Nodes (10): _Formatter, setup_file_log(), should_speak(), _r(), test_a_reply_that_asks_for_confirmation_is_always_spoken_even_when_stale(), test_a_stale_confirmation_is_never_skipped_so_no_unheard_pending_action_exists(), test_file_log_is_added_once_and_receives_records(), test_only_plain_care_and_companion_replies_may_be_skipped_as_stale() (+2 more)

### Community 68 - "Community 68"
Cohesion: 0.15
Nodes (12): fold(), _is_emergency_basic(), _ascii(), _devanagari(), format_bp(), parse_bp(), test_a_reading_does_not_replace_a_pending_question(), test_common_ways_of_saying_a_reading() (+4 more)

### Community 69 - "Community 69"
Cohesion: 0.22
Nodes (15): _add(), _clock(), test_bad_inputs_rejected(), test_create_and_list_keeps_name_and_dose_verbatim(), test_delete_medicine_removes_doses(), test_due_taken_is_self_reported_with_on_time_flag(), test_fixed_anchor_requires_time(), test_late_take_is_flagged_late_not_punished() (+7 more)

### Community 70 - "Community 70"
Cohesion: 0.19
Nodes (12): efold(), _epat(), gives_medical_advice(), has_failsafe_word(), has_health_word(), loanword_emergency(), mentions_cardiac(), _pat() (+4 more)

### Community 71 - "Community 71"
Cohesion: 0.15
Nodes (16): _pending(), _seed(), test_a_story_with_a_no_in_it_does_not_reject_the_pending_save(), test_bare_no_keeps_the_old_cancel_reply(), test_greeting_followed_by_a_request_is_the_request(), test_greeting_gets_a_fixed_greeting_not_an_error(), test_hearing_check_answers_yes_i_can_hear_you(), test_hearing_check_does_not_drop_an_open_reminder() (+8 more)

### Community 72 - "Community 72"
Cohesion: 0.20
Nodes (14): engine(), link(), NoLlm, test_a_media_turn_enters_the_conversation_history(), test_a_named_bhajan_keeps_the_singers_name_in_the_query(), test_a_refusal_plus_a_topic_change_becomes_the_fixed_line(), test_a_reminder_that_mentions_media_is_still_a_reminder(), test_media_control_stop() (+6 more)

### Community 73 - "Community 73"
Cohesion: 0.22
Nodes (16): channelFromUrl(), control(), CONTROLS, embedSrc(), fromUrl(), isYoutube(), MediaPlan, planAction() (+8 more)

### Community 74 - "Community 74"
Cohesion: 0.18
Nodes (14): _draft(), _pending(), test_bare_day_part_with_no_clock_word_still_uses_the_family_set_anchor(), test_clock_word_alone_leaves_the_time_open(), test_clock_word_without_a_readable_hour_asks_and_never_uses_the_wake_time(), test_day_part_said_earlier_is_remembered_when_the_hour_arrives(), test_filler_words_do_not_end_up_in_the_task(), test_hour_word_without_a_day_part_asks_am_or_pm() (+6 more)

### Community 75 - "Community 75"
Cohesion: 0.24
Nodes (15): _add_medicine(), _due(), _pending(), test_deflection_tells_family_only_after_yes(), test_distress_overrides_medicine_talk(), test_medicine_questions_are_deflected_not_answered(), test_medicine_word_in_followup_slot_is_refused(), test_no_after_taken_prompt_records_nothing() (+7 more)

### Community 76 - "Community 76"
Cohesion: 0.20
Nodes (14): actions(), pending(), test_a_long_care_command_is_a_care_command_not_a_story(), test_a_long_chat_sentence_does_not_replace_a_pending_reminder(), test_a_pending_caregiver_request_is_repeated(), test_a_pending_story_save_is_repeated_not_replaced(), test_a_real_story_is_still_offered_to_be_kept(), test_an_emergency_still_wins_over_a_pending_action() (+6 more)

### Community 77 - "Community 77"
Cohesion: 0.22
Nodes (13): ask(), ask_reasoning(), fallback_text(), reply_or_fallback(), _client(), test_ask_reasoning_parses_reply(), test_fallback_on_malformed_json(), test_fallback_on_network_error() (+5 more)

### Community 78 - "Community 78"
Cohesion: 0.18
Nodes (10): AlertNote, recentEmergencies(), now, loadAcked(), needsPopup(), saveAcked(), startEmergencyWatch(), now (+2 more)

### Community 79 - "Community 79"
Cohesion: 0.24
Nodes (8): Wellbeing, add(), _out(), recent(), today(), TodayOut, WellbeingIn, WellbeingOut

### Community 80 - "Community 80"
Cohesion: 0.18
Nodes (14): _due_medicine(), _reminders(), test_a_correction_replaces_the_one_just_saved(), test_a_long_story_is_kept_privately_without_asking(), test_a_reminder_is_saved_at_once_and_read_back(), test_after_the_window_nako_is_a_topic_decline_not_an_undo(), test_ghetli_records_a_due_medicine_at_once(), test_help_is_sent_at_once_and_says_where() (+6 more)

### Community 81 - "Community 81"
Cohesion: 0.26
Nodes (7): ActivityIn, ActivityOut, get_activity(), mark_seen(), record_activity(), _row(), _user()

### Community 82 - "Community 82"
Cohesion: 0.16
Nodes (5): vitest, confirmThen(), Listenable, startPolling(), FakeTarget

### Community 83 - "Community 83"
Cohesion: 0.29
Nodes (9): answer_checkin(), _heard(), list_checkins(), open_checkin(), _out(), postpone_checkin(), _user(), volunteer_checkin() (+1 more)

### Community 84 - "Community 84"
Cohesion: 0.23
Nodes (9): Llm, make(), sent(), test_a_care_turn_in_the_conversation_is_in_the_history_as_short_text(), test_a_long_care_turn_is_cut_short(), test_a_thirty_minute_silence_starts_a_new_conversation(), test_distress_drops_the_history(), test_medicine_turns_never_enter_the_llm_history() (+1 more)

### Community 85 - "Community 85"
Cohesion: 0.19
Nodes (5): main(), _load_env(), main(), post(), samples()

### Community 86 - "Community 86"
Cohesion: 0.16
Nodes (6): Fake, test_boundary_report_flags_each_category_and_counts_clean_replies(), test_intent_scoring_counts_valid_json_accuracy_and_skips_unscorable(), test_latency_tokens_and_medians(), test_sentence_set_is_twenty_real_first_then_distinct_eval_cases(), test_sentences_fall_back_to_cases_when_no_real_speech_is_present()

### Community 87 - "Community 87"
Cohesion: 0.25
Nodes (9): apply_plan(), build_plan(), _is_junk(), Item, main(), Plan, _print(), run() (+1 more)

### Community 88 - "Community 88"
Cohesion: 0.17
Nodes (11): collapse_repeats(), test_a_pending_answer_made_only_of_no_words_is_a_no(), test_a_pending_answer_made_only_of_yes_words_is_a_yes_at_any_length(), test_a_repetition_cannot_hide_an_emergency(), test_normal_speech_is_left_alone(), test_punctuation_and_case_do_not_hide_a_repetition(), test_repeated_phrases_collapse_too(), test_runs_of_three_or_more_collapse_to_one() (+3 more)

### Community 89 - "Community 89"
Cohesion: 0.23
Nodes (10): api, joinProblem(), joinTokenFrom(), statusFromError(), JoinCall(), Status, App(), params (+2 more)

### Community 90 - "Community 90"
Cohesion: 0.24
Nodes (11): AppLink, AppLinkInput, Contact, MediaStatus, KIND_LABELS, contacts, testUrl(), warning() (+3 more)

### Community 91 - "Community 91"
Cohesion: 0.24
Nodes (12): connectFeed(), FeedEvent, FeedStatus, isSeverity(), lastId(), mergeFeed(), parseMessage(), Severity (+4 more)

### Community 92 - "Community 92"
Cohesion: 0.19
Nodes (5): _call(), _fetch(), _load_env(), main(), verify()

### Community 93 - "Community 93"
Cohesion: 0.19
Nodes (6): notes(), test_distress_with_consent_off_alerts_nobody(), test_distress_with_consent_on_alerts_as_distress(), test_each_emergency_alerts_the_family_with_consent_off(), _cases(), test_real_transcript_gets_the_expected_intent_and_slots()

### Community 94 - "Community 94"
Cohesion: 0.20
Nodes (8): test_core_api_gets_the_livekit_settings_for_the_token_endpoint(), test_env_example_lists_every_llm_name(), test_llm_settings_reach_reasoning_and_the_llm_key_reaches_nothing_else(), test_the_web_app_never_calls_reasoning_directly(), test_the_web_app_uses_no_browser_speech_api(), test_web_dev_server_gets_the_variables_its_proxy_needs(), _vars(), _alt()

### Community 95 - "Community 95"
Cohesion: 0.14
Nodes (13): compilerOptions, isolatedModules, jsx, lib, module, moduleResolution, noEmit, noImplicitAny (+5 more)

### Community 97 - "Community 97"
Cohesion: 0.31
Nodes (8): configure_logging(), _client(), _ok(), test_a_failed_call_logs_the_error_type_only(), test_a_successful_call_logs_one_json_line_with_the_numbers(), test_configure_logging_is_idempotent(), test_configure_logging_turns_on_info_for_our_loggers_and_leaves_uvicorn_alone(), test_no_log_line_ever_holds_the_text_or_the_key()

### Community 98 - "Community 98"
Cohesion: 0.28
Nodes (10): _events(), _notes(), test_distress_with_consent_off_does_not_alert(), test_distress_with_consent_on_alerts_as_before(), test_emergency_with_consent_off_still_alerts(), test_emergency_with_consent_on_makes_exactly_one_alert(), test_every_emergency_is_alerted_not_deduplicated(), test_the_alert_does_not_claim_a_call_or_message_was_sent() (+2 more)

### Community 99 - "Community 99"
Cohesion: 0.24
Nodes (11): is_distress(), _son(), test_a_doctor_only_contact_falls_back_to_your_family(), test_consent_off_never_claims_the_family_was_told(), test_distress_caregiver_alert_requires_consent(), test_distress_detected(), test_distress_overrides_pending_and_never_executes(), test_distress_reply_makes_no_feeling_or_diagnosis_claims() (+3 more)

### Community 100 - "Community 100"
Cohesion: 0.27
Nodes (8): efold(), _epat(), fold(), has_phrase(), is_safety_phrase(), loanword_emergency(), normalize(), _word_regex()

### Community 101 - "Community 101"
Cohesion: 0.26
Nodes (7): Get-TunnelProcesses(), Get-TunnelUrlFromLog(), Start-PhoneTunnel(), Stop-Tunnel(), Test-PortListening(), Test-ServiceRunning(), Test-TunnelUrl()

### Community 102 - "Community 102"
Cohesion: 0.29
Nodes (9): add(), test_a_contact_of_another_user_cannot_be_used(), test_another_users_link_is_not_reachable(), test_family_can_add_list_edit_and_delete(), test_known_hosts_need_no_approval_and_subdomains_match(), test_unknown_host_needs_explicit_family_approval_and_is_flagged(), test_unsafe_urls_are_rejected_even_with_approval(), test_whatsapp_points_at_an_existing_contact_and_never_stores_a_number() (+1 more)

### Community 103 - "Community 103"
Cohesion: 0.23
Nodes (9): is_lonely(), _contact(), test_a_pending_question_still_wins(), test_distress_still_overrides_loneliness(), test_family_told_only_with_consent_and_once_a_day(), test_lonely_phrases(), test_not_lonely(), test_reply_names_the_family_and_keeps_listening() (+1 more)

### Community 104 - "Community 104"
Cohesion: 0.31
Nodes (6): build_sentences(), _load_settings(), main(), _pct(), run_companion(), summarize()

### Community 105 - "Community 105"
Cohesion: 0.35
Nodes (4): _at(), next_occurrence(), occurrence_end(), occurrence_on()

### Community 106 - "Community 106"
Cohesion: 0.35
Nodes (7): _class(), set_now(), test_a_weekly_appointment_appears_only_on_its_weekdays(), test_next_appointment_after_tuesdays_class_is_fridays(), test_next_appointment_on_monday_is_tuesdays_class(), test_one_off_appointment_behaviour_is_unchanged(), test_the_rule_starts_on_the_first_day_it_applies()

### Community 107 - "Community 107"
Cohesion: 0.27
Nodes (7): _pending(), _reminder(), _story(), test_a_pending_action_is_always_found_for_the_main_flows(), test_a_yes_after_a_safety_reply_confirms_nothing(), test_emergency_and_distress_replies_are_labelled_safety(), test_every_reply_that_leaves_a_pending_action_asks_for_confirmation()

### Community 108 - "Community 108"
Cohesion: 0.24
Nodes (8): _pending(), test_a_confirmed_action_lands_on_saved_and_a_refused_one_does_not(), test_a_safety_screen_follows_even_with_a_confirmation_pending(), test_a_tapped_yes_with_nothing_pending_is_refused_like_a_spoken_one(), test_a_yes_with_nothing_pending_is_not_saved(), test_screen_for_each_kind_of_reply(), test_tap_and_voice_answers_give_the_same_result(), test_turn_out_carries_the_screen()

### Community 109 - "Community 109"
Cohesion: 0.18
Nodes (10): enum, description, type, properties, action_type, payload, required, $schema (+2 more)

### Community 110 - "Community 110"
Cohesion: 0.24
Nodes (8): CheckinCardItem, DayCardRow, dayCardRows(), hhmm(), Mark, MARKS, NAMES, NOT_ASKED

### Community 111 - "Community 111"
Cohesion: 0.31
Nodes (6): _age(), _status(), test_a_fresh_question_is_still_pending(), test_a_late_yes_cannot_confirm_an_expired_action(), test_an_old_question_is_not_returned_and_is_marked_expired(), test_only_the_stale_ones_expire()

### Community 113 - "Community 113"
Cohesion: 0.27
Nodes (3): Draft, done(), Parsed

### Community 114 - "Community 114"
Cohesion: 0.33
Nodes (7): ActivityLine, activityLine(), ago(), clock(), QUIET_AFTER_WAKE_H, sameDay(), wakeAt()

### Community 115 - "Community 115"
Cohesion: 0.36
Nodes (6): Delivery, Card, DeliveryRow, deliveryRows(), DeliveryText, describeDelivery()

### Community 121 - "Community 121"
Cohesion: 0.33
Nodes (3): FakePlugin, STT, TTS

## Knowledge Gaps
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `TurnEngine` connect `Community 3` to `Community 0`, `Community 1`, `Community 128`, `Community 4`, `Community 8`, `Community 9`, `Community 11`, `Community 13`, `Community 17`, `Community 20`, `Community 24`, `Community 25`, `Community 27`, `Community 34`, `Community 43`, `Community 51`, `Community 53`, `Community 58`, `Community 60`, `Community 70`, `Community 72`, `Community 80`, `Community 84`, `Community 88`, `Community 93`, `Community 99`, `Community 108`, `Community 113`, `Community 117`, `Community 120`, `Community 124`, `Community 126`?**
  _High betweenness centrality (0.092) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `TurnEngine` (e.g. with `CoreClient` and `CoreError`) actually correct?**
  _`TurnEngine` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.04926819212533498 - nodes in this community are weakly interconnected._
- **Why does `CoreClient` connect `Community 0` to `Community 128`, `Community 1`, `Community 3`, `Community 4`, `Community 8`, `Community 9`, `Community 11`, `Community 13`, `Community 17`, `Community 20`, `Community 24`, `Community 25`, `Community 27`, `Community 34`, `Community 43`, `Community 51`, `Community 53`, `Community 58`, `Community 60`, `Community 63`, `Community 72`, `Community 80`, `Community 84`, `Community 88`, `Community 93`, `Community 99`, `Community 108`, `Community 117`, `Community 126`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `CoreClient` (e.g. with `TurnEngine` and `Tracker`) actually correct?**
  _`CoreClient` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.05350877192982456 - nodes in this community are weakly interconnected._
- **Why does `time` connect `Community 62` to `Community 1`, `Community 13`, `Community 26`, `Community 27`, `Community 29`, `Community 31`, `Community 35`, `Community 38`, `Community 42`, `Community 44`, `Community 45`, `Community 49`, `Community 50`, `Community 55`, `Community 56`, `Community 57`, `Community 66`, `Community 85`, `Community 104`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._