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

- problems: 4
  - unmigrated reference tests/test_intent_judge.py:174 (string): assert "Jarvisring" not in prompt2
  - unmigrated reference tests/test_wake_alias_boundaries.py:12 (string): 'jarvisian is a made-up word',
  - unmigrated reference tests/test_wake_alias_boundaries.py:52 (string): ('atlas explain jarvisian philosophy', 'explain jarvisian philosophy'),
  - unmigrated reference tests/test_wake_alias_boundaries.py:52 (string): ('atlas explain jarvisian philosophy', 'explain jarvisian philosophy'),
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
  - docs/atlas-migration/last-run.md (22 lignes): migration reports
  - scripts/atlas_migration/legacy_compat.py.tmpl (8 lignes): migration templates (name the former name by design)
  - scripts/atlas_migration/test_atlas_legacy_compat.py.tmpl (14 lignes): migration templates (name the former name by design)
  - scripts/migrate_to_atlas.py (16 lignes): migration tooling (names the former name by design)
  - tests/test_atlas_migration_script.py (42 lignes): tests of the migration tooling
  - website/build.py (3 lignes): public upstream website, separate deliverable: owner decision
  - website/getting-started.html (4 lignes): public upstream website, separate deliverable: owner decision
  - website/home.html (8 lignes): public upstream website, separate deliverable: owner decision
  - website/layout.html (4 lignes): public upstream website, separate deliverable: owner decision
  - website/privacy.html (8 lignes): public upstream website, separate deliverable: owner decision
  - website/site.json (10 lignes): public upstream website, separate deliverable: owner decision
  - website/website.spec.md (1 lignes): public upstream website, separate deliverable: owner decision

## Comparaison des tests

```
(missing)
```

## Tests apres migration (fin du journal)

```
(missing)
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
45 failed, 6267 passed, 3 skipped, 218 deselected, 3 warnings in 226.90s (0:03:46)

```

## Windows (fin du journal)

```
(missing)
```
