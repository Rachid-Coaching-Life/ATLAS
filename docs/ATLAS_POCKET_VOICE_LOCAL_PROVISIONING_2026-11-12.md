# ATLAS — Profil vocal Pocket TTS, préparation privée sur Windows

Statut : script et tests synthétiques préparés ; export de la véritable voix personnelle sur GTR7 non encore exécuté.

## Preuves existantes

Sur GitHub Actions Windows, la PR #37 a confirmé le binaire officiel Pocket TTS Rust 3.3.0 (release du dépôt Kyutai v4.0.1), la génération française avec la voix publique Estelle, puis une nouvelle génération avec endpoint HF bloqué. Les tests du pont de synthèse et des interruptions ont réussi sur le même run. Ces résultats ne prouvent pas le clonage de la voix personnelle ni la vitesse réelle sur GTR7.

## Une seule procédure prévue

Le script scripts/prepare_pocket_voice.py utilise un seul WAV de référence de 5 à 30 secondes et crée un nouveau profil safetensors localement. La référence personnelle candidate de 15 secondes est conservée hors dépôt. Il faut d'abord disposer du binaire officiel pocket-tts.exe et des chemins privés existants sur le GTR7. Le script ne copie aucune donnée vers GitHub.

Archive officielle : pocket-tts-3.3.0-x86_64-pc-windows-msvc.zip.
Empreinte SHA-256 : 98753041f2e65744b989776f87bccb93f1f574a08afe1890c5427ec94cd6309c.

Exemple de commande PowerShell (CHEMIN_PRIVE doit être remplacé par un chemin réellement existant sur le GTR7) :

~~~powershell
python scripts/prepare_pocket_voice.py --binary "C:\CHEMIN_PRIVE\pocket-tts.exe" --reference-wav "C:\CHEMIN_PRIVE\reference_15s.wav" --output "$env:LOCALAPPDATA\ATLAS\private\pocket\voice_french.safetensors" --allow-initial-download
~~~

La commande ne doit pas être lancée avant qualification du script sur Windows. L'accès au modèle Kyutai permettant le clonage vocal nécessite que le compte Hugging Face ait personnellement accepté les conditions et soit authentifié sur le GTR7 ; l'autorisation d'utiliser les enregistrements dans ATLAS a déjà été accordée.

## Comportement du script

- Vérifie les chemins absolus, le binaire version 3.3.0, le WAV mono PCM16, une durée de 5 à 30 secondes et un signal non silencieux.
- Refuse les dossiers situés dans un dépôt Git, les profils existants et les sorties via lien symbolique.
- Sans --allow-initial-download, bloque l'endpoint HF distant. Avec cette option, seul l'export initial tente d'obtenir les poids autorisés, avec le compte connecté ; aucun WAV privé n'est téléchargé vers le cloud par le script.
- Vérifie ensuite une génération réelle depuis le profil exporté avec HF_ENDPOINT local inaccessible ; inspecte le WAV (format, durée et signal).
- Publie le profil final de façon atomique uniquement après réussite, sans écraser un profil existant ; nettoie les fichiers temporaires.
- Capture les sorties de Pocket TTS sans afficher les chemins personnels ni le token.

Les tests Python du script utilisent seulement des WAV et des poids fictifs. Ils vérifient les contrats techniques, la confidentialité des sorties, le refus d'écrasement, la suppression en cas d'échec, le respect du hors ligne et le refus d'export dans Git.

## Non validé à ce stade

L'accès effectif aux poids français avec clonage depuis le GTR7, la création du profil privé, la fidélité du timbre et la latence restent NON VÉRIFIÉS. Piper reste le moteur par défaut et aucune configuration personnelle du GTR7 n'est modifiée par cette PR.

Il est interdit de committer un WAV de Rachid, une empreinte vocale, un profil safetensors ou un identifiant de Hugging Face.
