# ATLAS — Préparation contrôlée de la voix personnalisée (12 novembre 2026)

## Diagnostic vérifié

- `src/atlas/output/tts.py` : Piper français générique par défaut ; Chatterbox sait transmettre `audio_prompt_path` à `generate()`.
- `src/atlas/config.py` : `tts_engine="piper"`, `tts_chatterbox_audio_prompt=None` par défaut. La configuration personnelle sur Windows **n'a pas été consultée**.
- `requirements.txt` : **`chatterbox-tts==0.1.2`**, daté du 13 juin 2025. La documentation officielle distingue `ChatterboxTTS` (original, exemple anglais) de `ChatterboxMultilingualTTS` (français avec `language_id="fr"`). Le multilingue a été publié dans les versions ultérieures, dès septembre 2025. Voir https://github.com/resemble-ai/chatterbox et https://pypi.org/project/chatterbox-tts/.
- Le dépôt ne démontre **ni clonage effectif de la voix de Rachid ni adaptation de la reconnaissance vocale**. Le paramètre de référence ne constitue pas une preuve d'une voix reproduite fidèlement.
- Le modèle Chatterbox est annoncé **non maintenu depuis août 2026** par son auteur. Cette dette de maintenance doit être étudiée avant toute modification des dépendances.

## Correction isolée dans cette branche

Sans activer Chatterbox, sans modifier les modèles ni la configuration :
- Refuser un chemin relatif, un fichier inexistant, non WAV, un lien symbolique direct, un en-tête WAV non reconnu ou un fichier illisible **avant le chargement lourd** du moteur.
- Garder les messages d'échec génériques ; **ne jamais imprimer le chemin de l'enregistrement personnel**.
- Tester avec un WAV synthétique (silence) fabriqué dans un dossier temporaire. Vérifier l'argument transmis à `generate()` avec un modèle simulé qui s'arrête avant lecture sonore.
- Piper reste sélectionné par défaut. Aucun corpus personnel ni artefact biométrique dans GitHub.

## Décision technique encore ouverte — compatibilité française

Pour reproduire la voix en français, examiner dans une **PR distincte** la compatibilité du backend multilingue officiel (`ChatterboxMultilingualTTS`, `language_id="fr"`) avec la pile déjà installée, Windows et les ressources du GTR7. Ne pas remplacer `chatterbox-tts==0.1.2` ni télécharger les poids avant d'avoir établi la compatibilité, les versions des dépendances et les contraintes de latence. Vérifier également la solution de repli Piper et les interruptions.

## Ce qui reste non vérifié

- Choix et qualité subjective d'un extrait de référence à partir des fichiers privés fournis.
- Intelligibilité française et ressemblance réelle avec la voix de Rachid.
- Temps de génération, mémoire, lecture audio et robustesse sur GTR7.
- La voie reconnaissance (corpus A) est **distincte** du clonage TTS (corpus B/C).
- Animation labiale, clignements et flottement : chantier ultérieur sans modification du portrait approuvé, voir `docs/ATLAS_AVATAR_ORIGINAL_ANIMATION_AUDIT_2026-11-11.md`.

**Statut : validation de chemin et tests simulés seulement ; voix personnalisée NON validée.**
