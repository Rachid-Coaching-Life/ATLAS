# Migration jarvis -> atlas: dernier run automatise

| Etape | Resultat |
| --- | --- |
| migrate | success |
| windows | success |

## Application

- problems: 0
- conflicts: 0
- warnings: 0
- chemins renommes: 129; fichiers modifies: 505

## Verification

- problems: 0
- conflicts: 0
- warnings: 5
  - to review (spelling variant) src/atlas/dictation/dictation_engine.py:431: """Apply custom dictionary corrections to transcribed text.
  - upstream identifier left for an owner decision .agents/skills/triage/SKILL.md:50: - **Untriaged**: no owner (`isair`) reply yet. Act now.
  - upstream identifier left for an owner decision .agents/skills/triage/SKILL.md:52: - **Owner tracking**: filed by `isair` as an internal task. Assess its current implementation and next action under the 
  - upstream identifier left for an owner decision .github/FUNDING.yml:5: github: [isair]
  - upstream identifier left for an owner decision .github/FUNDING.yml:8: ko_fi: isair
- assertions negatives conservees (absence de l'ancien nom): 7
  - tests/test_atlas_package_migration.py:24: assert "jarvis" not in result.lower()
  - tests/test_atlas_self_introduction.py:55: assert "🤖 Jarvis" not in output
  - tests/test_chat_submission.py:852: assert "🤖 Jarvis" not in activity
  - tests/test_chat_window.py:908: assert all("You:" not in t and "Jarvis:" not in t for t in texts)
  - tests/test_issue_report_flow.py:311: assert "Jarvis" not in dialog.expected_input.placeholderText()
  - tests/test_system_prompt.py:19: assert "named Jarvis" not in prompt
  - tests/test_wake_alias_boundaries.py:93: assert 'Jarvis' not in judge._normalize_aliases(heard)
- exceptions justifiees:
  - .github/workflows/atlas-core-rename.yml (4 lignes): workflow file: GITHUB_TOKEN cannot push workflow changes, migrate it separately
  - .github/workflows/build-desktop.yml (27 lignes): workflow file: GITHUB_TOKEN cannot push workflow changes, migrate it separately
  - .github/workflows/public-site.yml (3 lignes): workflow file: GITHUB_TOKEN cannot push workflow changes, migrate it separately
  - .github/workflows/release-smoke.yml (14 lignes): workflow file: GITHUB_TOKEN cannot push workflow changes, migrate it separately
  - .github/workflows/release.yml (9 lignes): workflow file: GITHUB_TOKEN cannot push workflow changes, migrate it separately
  - .github/workflows/tests.yml (2 lignes): workflow file: GITHUB_TOKEN cannot push workflow changes, migrate it separately
  - LICENSE (1 lignes): licence or third-party notice
  - docs/atlas-migration/last-run.md (20 lignes): migration reports
  - scripts/atlas_migration/legacy_compat.py.tmpl (8 lignes): migration templates (name the former name by design)
  - scripts/atlas_migration/test_atlas_legacy_compat.py.tmpl (14 lignes): migration templates (name the former name by design)
  - scripts/migrate_to_atlas.py (21 lignes): migration tooling (names the former name by design)
  - tests/test_atlas_migration_script.py (61 lignes): tests of the migration tooling
  - website/build.py (3 lignes): public upstream website, separate deliverable: owner decision
  - website/getting-started.html (4 lignes): public upstream website, separate deliverable: owner decision
  - website/home.html (8 lignes): public upstream website, separate deliverable: owner decision
  - website/layout.html (4 lignes): public upstream website, separate deliverable: owner decision
  - website/privacy.html (8 lignes): public upstream website, separate deliverable: owner decision
  - website/site.json (10 lignes): public upstream website, separate deliverable: owner decision
  - website/website.spec.md (1 lignes): public upstream website, separate deliverable: owner decision

## Comparaison des tests

```
baseline: 6319 tests, 45 failing
after:    6329 tests, 39 failing

```

## Tests apres migration (fin du journal)

```
  -         'ATLAS, tell me the weather',
  -         'en',
  -     ),
  - ]
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
FAILED tests/tools/builtin/test_web_search.py::TestLanguagePlumbingEndToEnd::test_listener_passes_detected_language_to_reply_engine - AttributeError: 'VoiceListener' object has no attribute 'state_manager'
39 failed, 6287 passed, 3 skipped, 218 deselected, 3 warnings in 191.10s (0:03:11)

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
45 failed, 6271 passed, 3 skipped, 218 deselected, 3 warnings in 193.65s (0:03:13)

```

## Windows (fin du journal)

```
166163 INFO: Including run-time hook 'pyi_rth_inspect.py' from 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\PyInstaller\\hooks\\rthooks'
166165 INFO: Including run-time hook 'pyi_rth_pkgutil.py' from 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\PyInstaller\\hooks\\rthooks'
166167 INFO: Including run-time hook 'pyi_rth_setuptools.py' from 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\PyInstaller\\hooks\\rthooks'
166169 INFO: Including run-time hook 'pyi_rth_pkgres.py' from 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\PyInstaller\\hooks\\rthooks'
166174 INFO: Including run-time hook 'pyi_rth_pywintypes.py' from 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\_pyinstaller_hooks_contrib\\rthooks'
166174 INFO: Including run-time hook 'pyi_rth_pythoncom.py' from 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\_pyinstaller_hooks_contrib\\rthooks'
166175 INFO: Including run-time hook 'pyi_rth_pyqt6.py' from 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\PyInstaller\\hooks\\rthooks'
166177 INFO: Processing pre-find-module-path hook 'hook-_pyi_rth_utils.py' from 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\PyInstaller\\hooks\\pre_find_module_path'
166178 INFO: Processing standard module hook 'hook-_pyi_rth_utils.py' from 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\PyInstaller\\hooks'
166181 INFO: Including run-time hook 'pyi_rth_multiprocessing.py' from 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\PyInstaller\\hooks\\rthooks'
166312 INFO: Creating base_library.zip...
166335 INFO: Looking for dynamic libraries
C:\hostedtoolcache\windows\Python\3.11.9\x64\Lib\site-packages\PyInstaller\building\build_main.py:227: UserWarning: The numpy.array_api submodule is still experimental. See NEP 47.
  __import__(package)
pygame 2.6.1 (SDL 2.28.4, Python 3.11.9)
Hello from the pygame community. https://www.pygame.org/contribute.html
169525 INFO: Extra DLL search directories (AddDllDirectory): ['C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\PyQt6\\Qt6\\bin', 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\faiss_cpu.libs', 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\numpy.libs', 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\ctranslate2', 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\av.libs', 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\curl_cffi.libs', 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\pygame']
169525 INFO: Extra DLL search directories (PATH): []
176102 WARNING: Library not found: could not resolve 'miniupnpc.dll', dependency of 'C:\\hostedtoolcache\\windows\\Python\\3.11.9\\x64\\Lib\\site-packages\\miniupnpc.cp311-win_amd64.pyd'.
176295 INFO: Warnings written to D:\a\ATLAS\ATLAS\build\atlas_desktop\warn-atlas_desktop.txt
176564 INFO: Graph cross-reference written to D:\a\ATLAS\ATLAS\build\atlas_desktop\xref-atlas_desktop.html
176736 INFO: checking PYZ
176736 INFO: Building PYZ because PYZ-00.toc is non existent
176736 INFO: Building PYZ (ZlibArchive) D:\a\ATLAS\ATLAS\build\atlas_desktop\PYZ-00.pyz
178886 INFO: Building PYZ (ZlibArchive) D:\a\ATLAS\ATLAS\build\atlas_desktop\PYZ-00.pyz completed successfully.
178942 INFO: checking PKG
178942 INFO: Building PKG because PKG-00.toc is non existent
178942 INFO: Building PKG (CArchive) ATLAS.pkg
179032 INFO: Building PKG (CArchive) ATLAS.pkg completed successfully.
179032 INFO: Bootloader C:\hostedtoolcache\windows\Python\3.11.9\x64\Lib\site-packages\PyInstaller\bootloader\Windows-64bit-intel\runw.exe
179034 INFO: checking EXE
179034 INFO: Building EXE because EXE-00.toc is non existent
179034 INFO: Building EXE from EXE-00.toc
179034 INFO: Copying bootloader EXE to D:\a\ATLAS\ATLAS\build\atlas_desktop\ATLAS.exe
179036 INFO: Copying icon to EXE
179038 INFO: Copying 0 resources to EXE
179038 INFO: Embedding manifest in EXE
179040 INFO: Appending PKG archive to EXE
179050 INFO: Fixing EXE headers
179181 INFO: Building EXE from EXE-00.toc completed successfully.
179305 INFO: checking COLLECT
179305 INFO: Building COLLECT because COLLECT-00.toc is non existent
179305 INFO: Building COLLECT COLLECT-00.toc
182449 INFO: Building COLLECT COLLECT-00.toc completed successfully.
182537 INFO: Build complete! The results are available in: D:\a\ATLAS\ATLAS\dist
Bundling Piper espeak-ng-data from C:\hostedtoolcache\windows\Python\3.11.9\x64\Lib\site-packages\piper\espeak-ng-data
Bundling Piper tashkeel from C:\hostedtoolcache\windows\Python\3.11.9\x64\Lib\site-packages\piper\tashkeel
Bundling tzdata for zoneinfo support on Windows
pygame 2.6.1 (SDL 2.28.4, Python 3.11.9)
Hello from the pygame community. https://www.pygame.org/contribute.html
Excluding system DLL (use VC++ Redistributable): vcruntime140.dll
Excluding system DLL (use VC++ Redistributable): msvcp140.dll
Excluding system DLL (use VC++ Redistributable): vcruntime140_1.dll
Excluding system DLL (use VC++ Redistributable): PyQt6\Qt6\bin\MSVCP140.dll
Excluding system DLL (use VC++ Redistributable): PyQt6\Qt6\bin\VCRUNTIME140_1.dll
Excluding system DLL (use VC++ Redistributable): PyQt6\Qt6\bin\VCRUNTIME140.dll
Excluding system DLL (use VC++ Redistributable): PyQt6\Qt6\bin\MSVCP140_1.dll
Excluding system DLL (use VC++ Redistributable): PyQt6\Qt6\bin\MSVCP140_2.dll
Excluding system DLL (use VC++ Redistributable): ucrtbase.dll

```
