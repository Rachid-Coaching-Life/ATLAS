# Migration jarvis -> atlas: dernier run automatise

| Etape | Resultat |
| --- | --- |
| migrate | failure |
| windows | skipped |

## Application

- problems: 2
  - cannot rename src/jarvis -> src/atlas (blocked: ['src/jarvis/dictation/history.py'])
  - cannot rename src/jarvis -> src/atlas (blocked: ['src/jarvis/dictation/history.py'])
- conflicts: 0
- warnings: 0
- chemins renommes: 2; fichiers modifies: 504

## Verification

(rapport absent)

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
45 failed, 6265 passed, 3 skipped, 218 deselected, 3 warnings in 215.11s (0:03:35)

```

## Windows (fin du journal)

```
(missing)
```
