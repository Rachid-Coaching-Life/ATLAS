# Migration jarvis -> atlas: dernier run automatise

| Etape | Resultat |
| --- | --- |
| migrate | failure |
| windows | skipped |

## Application

- problems: 0
- conflicts: 0
- warnings: 0
- chemins renommes: 129; fichiers modifies: 505

## Verification

- problems: 0
- conflicts: 0
- warnings: 10
  - to review (spelling variant) src/atlas/dictation/dictation_engine.py:431: """Apply custom dictionary corrections to transcribed text.
  - upstream identifier left for an owner decision .agents/skills/triage/SKILL.md:29: gh api graphql -f query='{repository(owner:"isair",name:"atlas"){discussions(first:30,states:OPEN,orderBy:{field:UPDATED
  - upstream identifier left for an owner decision .agents/skills/triage/SKILL.md:50: - **Untriaged**: no owner (`isair`) reply yet. Act now.
  - upstream identifier left for an owner decision .agents/skills/triage/SKILL.md:52: - **Owner tracking**: filed by `isair` as an internal task. Assess its current implementation and next action under the 
  - upstream identifier left for an owner decision .agents/skills/triage/SKILL.md:205: gh api graphql -f query='{repository(owner:"isair",name:"atlas"){discussion(number:N){comments(last:5){nodes{id author{l
  - upstream identifier left for an owner decision .github/FUNDING.yml:5: github: [isair]
  - upstream identifier left for an owner decision .github/FUNDING.yml:8: ko_fi: isair
  - upstream identifier left for an owner decision tests/test_public_website.py:73: 'https://isair.github.io/atlas/',
  - upstream identifier left for an owner decision tests/test_public_website.py:161: builder.build_site(output, base_url='https://isair.github.io/atlas/')
  - upstream identifier left for an owner decision tests/test_public_website.py:163: assert 'https://isair.github.io' not in (output / 'sitemap.xml').read_text()
- exceptions justifiees:
  - .github/workflows/atlas-core-rename.yml (4 lignes): workflow file: GITHUB_TOKEN cannot push workflow changes, migrate it separately
  - .github/workflows/build-desktop.yml (27 lignes): workflow file: GITHUB_TOKEN cannot push workflow changes, migrate it separately
  - .github/workflows/public-site.yml (3 lignes): workflow file: GITHUB_TOKEN cannot push workflow changes, migrate it separately
  - .github/workflows/release-smoke.yml (14 lignes): workflow file: GITHUB_TOKEN cannot push workflow changes, migrate it separately
  - .github/workflows/release.yml (9 lignes): workflow file: GITHUB_TOKEN cannot push workflow changes, migrate it separately
  - .github/workflows/tests.yml (2 lignes): workflow file: GITHUB_TOKEN cannot push workflow changes, migrate it separately
  - LICENSE (1 lignes): licence or third-party notice
  - docs/atlas-migration/last-run.md (24 lignes): migration reports
  - scripts/atlas_migration/legacy_compat.py.tmpl (8 lignes): migration templates (name the former name by design)
  - scripts/atlas_migration/test_atlas_legacy_compat.py.tmpl (14 lignes): migration templates (name the former name by design)
  - scripts/migrate_to_atlas.py (18 lignes): migration tooling (names the former name by design)
  - tests/test_atlas_migration_script.py (45 lignes): tests of the migration tooling
  - website/build.py (3 lignes): public upstream website, separate deliverable: owner decision
  - website/getting-started.html (4 lignes): public upstream website, separate deliverable: owner decision
  - website/home.html (8 lignes): public upstream website, separate deliverable: owner decision
  - website/layout.html (4 lignes): public upstream website, separate deliverable: owner decision
  - website/privacy.html (8 lignes): public upstream website, separate deliverable: owner decision
  - website/site.json (10 lignes): public upstream website, separate deliverable: owner decision
  - website/website.spec.md (1 lignes): public upstream website, separate deliverable: owner decision

## Comparaison des tests

```
baseline: 6316 tests, 45 failing
after:    6326 tests, 43 failing
REGRESSION: tests.test_atlas_self_introduction::test_self_intro_needs_no_llm_or_tools_and_preserves_voice_and_memory
REGRESSION: tests.test_issue_report_flow::test_atlas_issue_dialog_is_french_and_targets_the_atlas_repository
REGRESSION: tests.test_wake_alias_boundaries::test_primary_approximation_and_exact_alias_remain_usable[atlas-joris-jarvas]
REGRESSION: tests.test_wake_detection.TestWakeWordDetection::test_fuzzy_match

```

## Tests apres migration (fin du journal)

```
FAILED tests/test_voice_query_language.py::test_pending_reply_language_tracks_accepted_request[whitespace] - AssertionError: assert [] == [('ATLAS, tel...ather', 'en')]
  
  Right contains one more item: ('ATLAS, tell me the weather', 'en')
  
  Full diff:
  + []
  - [
  -     (
  -         'ATLAS, tell me the weather',
  -         'en',
  -     ),
  - ]
FAILED tests/test_voice_query_language.py::test_pending_reply_language_tracks_accepted_request[repetition] - AssertionError: assert [] == [('ATLAS, tel...ather', 'en')]
  
  Right contains one more item: ('ATLAS, tell me the weather', 'en')
  
  Full diff:
  + []
  - [
  -     (
  -         'ATLAS, tell me the weather',
  -         'en',
  -     ),
  - ]
FAILED tests/test_voice_query_language.py::test_pending_reply_language_tracks_accepted_request[echo] - AssertionError: assert [] == [('ATLAS, tel...ather', 'en')]
  
  Right contains one more item: ('ATLAS, tell me the weather', 'en')
  
  Full diff:
  + []
  - [
  -     (
  -         'ATLAS, tell me the weather',
  -         'en',
  -     ),
  - ]
FAILED tests/test_voice_query_language.py::test_pending_reply_language_tracks_accepted_request[undirected] - AssertionError: assert 'ATLAS, tell ...S, pas à toi.' == 'ATLAS, tell me the weather'
  
  - ATLAS, tell me the weather
  + ATLAS, tell me the weather Je parle à ATLAS, pas à toi.
FAILED tests/test_voice_query_language.py::test_pending_reply_language_tracks_accepted_request[accepted] - AssertionError: assert 'ATLAS, tell ..., 오늘 날씨는 어때요?' == 'ATLAS, 오늘 날씨는 어때요?'
  
  - ATLAS, 오늘 날씨는 어때요?
  + ATLAS, tell me the weather ATLAS, 오늘 날씨는 어때요?
FAILED tests/test_voice_query_language.py::test_pending_reply_language_tracks_accepted_request[unknown] - AssertionError: assert 'ATLAS, tell ...the forecast.' == 'ATLAS, provide the forecast.'
  
  - ATLAS, provide the forecast.
  + ATLAS, tell me the weather ATLAS, provide the forecast.
FAILED tests/test_voice_tasks.py::test_live_voice_query_routes_to_real_task_and_speaks_success - AttributeError: 'VoiceListener' object has no attribute 'state_manager'
FAILED tests/test_voice_tasks.py::test_voice_ambiguity_asks_followup_then_uses_named_folder - AttributeError: 'VoiceListener' object has no attribute 'state_manager'
FAILED tests/test_voice_tasks.py::test_non_task_voice_query_keeps_existing_reply_engine - AttributeError: 'VoiceListener' object has no attribute 'state_manager'
FAILED tests/test_voice_tasks.py::test_voice_destructive_compound_file_request_fails_closed - AttributeError: 'VoiceListener' object has no attribute 'state_manager'
FAILED tests/test_voice_tasks.py::test_incomplete_voice_search_requires_folder_before_opening - AttributeError: 'VoiceListener' object has no attribute 'state_manager'
FAILED tests/test_wake_alias_boundaries.py::test_primary_approximation_and_exact_alias_remain_usable[atlas-joris-jarvas] - AssertionError: assert False
 +  where False = is_wake_word_detected('jarvas, hello', 'atlas', ['joris'])
FAILED tests/test_wake_detection.py::TestWakeWordDetection::test_fuzzy_match - AssertionError: assert False is True
 +  where False = is_wake_word_detected('hey jarvas', 'atlas', [], fuzzy_ratio=0.78)
FAILED tests/tools/builtin/test_web_search.py::TestLanguagePlumbingEndToEnd::test_listener_passes_detected_language_to_reply_engine - AttributeError: 'VoiceListener' object has no attribute 'state_manager'
43 failed, 6280 passed, 3 skipped, 218 deselected, 3 warnings in 224.08s (0:03:44)

```

## Tests avant migration (fin du journal)

```
  -         'Jarvis, tell me the weather',
  -         'en',
  -     ),
  - ]
FAILED tests/test_voice_query_language.py::test_pending_reply_language_tracks_accepted_request[whitespace] - AssertionError: assert [] == [('Jarvis, te...ather', 'en')]
  
  Right contains one more item: ('Jarvis, tell me the weather', 'en')
  
  Full diff:
  + []
  - [
  -     (
  -         'Jarvis, tell me the weather',
  -         'en',
  -     ),
  - ]
FAILED tests/test_voice_query_language.py::test_pending_reply_language_tracks_accepted_request[repetition] - AssertionError: assert [] == [('Jarvis, te...ather', 'en')]
  
  Right contains one more item: ('Jarvis, tell me the weather', 'en')
  
  Full diff:
  + []
  - [
  -     (
  -         'Jarvis, tell me the weather',
  -         'en',
  -     ),
  - ]
FAILED tests/test_voice_query_language.py::test_pending_reply_language_tracks_accepted_request[echo] - AssertionError: assert [] == [('Jarvis, te...ather', 'en')]
  
  Right contains one more item: ('Jarvis, tell me the weather', 'en')
  
  Full diff:
  + []
  - [
  -     (
  -         'Jarvis, tell me the weather',
  -         'en',
  -     ),
  - ]
FAILED tests/test_voice_query_language.py::test_pending_reply_language_tracks_accepted_request[undirected] - AssertionError: assert 'Jarvis, tell...s, pas à toi.' == 'Jarvis, tell me the weather'
  
  - Jarvis, tell me the weather
  + Jarvis, tell me the weather Je parle à Jarvis, pas à toi.
FAILED tests/test_voice_query_language.py::test_pending_reply_language_tracks_accepted_request[accepted] - AssertionError: assert 'Jarvis, tell..., 오늘 날씨는 어때요?' == 'Jarvis, 오늘 날씨는 어때요?'
  
  - Jarvis, 오늘 날씨는 어때요?
  + Jarvis, tell me the weather Jarvis, 오늘 날씨는 어때요?
FAILED tests/test_voice_query_language.py::test_pending_reply_language_tracks_accepted_request[unknown] - AssertionError: assert 'Jarvis, tell...the forecast.' == 'Jarvis, prov...the forecast.'
  
  - Jarvis, provide the forecast.
  + Jarvis, tell me the weather Jarvis, provide the forecast.
FAILED tests/test_voice_tasks.py::test_live_voice_query_routes_to_real_task_and_speaks_success - AttributeError: 'VoiceListener' object has no attribute 'state_manager'
FAILED tests/test_voice_tasks.py::test_voice_ambiguity_asks_followup_then_uses_named_folder - AttributeError: 'VoiceListener' object has no attribute 'state_manager'
FAILED tests/test_voice_tasks.py::test_non_task_voice_query_keeps_existing_reply_engine - AttributeError: 'VoiceListener' object has no attribute 'state_manager'
FAILED tests/test_voice_tasks.py::test_voice_destructive_compound_file_request_fails_closed - AttributeError: 'VoiceListener' object has no attribute 'state_manager'
FAILED tests/test_voice_tasks.py::test_incomplete_voice_search_requires_folder_before_opening - AttributeError: 'VoiceListener' object has no attribute 'state_manager'
FAILED tests/tools/builtin/test_web_search.py::TestLanguagePlumbingEndToEnd::test_listener_passes_detected_language_to_reply_engine - AttributeError: 'VoiceListener' object has no attribute 'state_manager'
45 failed, 6268 passed, 3 skipped, 218 deselected, 3 warnings in 226.28s (0:03:46)

```

## Windows (fin du journal)

```
(missing)
```
