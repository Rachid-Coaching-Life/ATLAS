# ATLAS — Paquet vocal privé sans WAV

Commit source : 19e0d47ddb58c4ffaa0d70dae12518ad2ffe3946
Dépôt : Rachid-Coaching-Life/ATLAS, PR n°38.

Ce paquet contient uniquement les trois scripts de cette version, leur manifeste,
les empreintes et cette notice. Aucun enregistrement, profil vocal, jeton,
exécutable Pocket TTS ou poids de modèle n'est inclus. Aucun logiciel n'a été
installé sur le GTR7 lors de sa préparation. Aucun paramètre ATLAS ou Piper n'a
été modifié. Le ZIP privé précédent n'étant pas accessible, aucune comparaison
avec celui-ci n'est revendiquée.

## Contenu exact

- PREPARER_MA_VOIX_ATLAS.cmd
- scripts/atlas_voice_setup.py
- scripts/prepare_pocket_voice.py
- LIRE_AVANT_UTILISATION.md
- CONTENU.json
- SHA256SUMS.txt

Les deux fichiers Python sont identiques, octet pour octet, aux blobs Git.
Le CMD utilise CRLF, comme prescrit par .gitattributes ; seules ses fins de ligne
sont converties. CONTENU.json donne les empreintes Git et celles du paquet.
SHA256SUMS.txt contrôle les cinq autres fichiers, pas lui-même. Le SHA-256 du ZIP
est fourni séparément avec le livrable : le comparer avant extraction. Des
empreintes internes seules ne prouvent pas l'origine d'une archive altérée.

## Ajouter localement l'extrait personnel

Aucun WAV personnel autorisé n'a été trouvé pendant la préparation. Ne pas
utiliser de fichier provenant d'un dossier de tests. Après extraction dans un
dossier privé local hors Git, ajouter une COPIE de l'extrait personnel approuvé
de 15 secondes à la racine, au même niveau que le CMD, sous le nom EXACT :

ATLAS_reference_vocale_C04_15s_candidate.wav

Conserver l'original intact ailleurs dans le stockage privé. Ce doit être un
véritable WAV PCM mono 16 bits ; le script accepte 8–96 kHz et 5–30 secondes,
refuse un fichier tronqué ou insuffisamment sonore. Le nom et la durée ne
prouvent ni l'identité du locuteur ni la qualité de l'extrait. Ne pas convertir,
remplacer ou récupérer un enregistrement inconnu automatiquement.

L'ajout du WAV change le contenu du dossier privé mais pas les scripts ni leurs
empreintes. Il n'est volontairement pas ajouté au manifeste public du code.
Ne jamais envoyer le dossier complété, le WAV, un profil ou un jeton à GitHub.

## Contrôle préalable Windows, avant toute exécution de préparation

1. Extraire entièrement le ZIP, sans lancer le CMD depuis la vue compressée.
   Utiliser un dossier LOCAL privé hors Git, hors synchronisation cloud, sans
   chemin réseau, lien symbolique, jonction ou reparse point. Conserver le
   sous-dossier scripts. Vérifier les ACL : pas d'accès pour d'autres utilisateurs
   ordinaires ; conserver les accès de maintenance légitimes nécessaires.
2. Ouvrir PowerShell dans le dossier extrait contenant le CMD. Contrôler les
   empreintes avec le bloc ci-dessous, AVANT d'ajouter le WAV ou de lancer le CMD.
3. Vérifier la version réellement choisie par `py -3 --version`, ou à défaut
   `python --version`. La CI Windows de référence utilise Python 3.11 ; d'autres
   versions et l'environnement du GTR7 ne sont pas validés par ce paquet.
4. Confirmer que LOCALAPPDATA désigne le dossier local attendu. La destination
   prévue est %LOCALAPPDATA%\ATLAS\private\pocket, avec le moteur dans engine
   et le profil final voice_french.safetensors. Inventorier ce qui existe déjà.
   Un profil existant est refusé, jamais remplacé. Ne pas supprimer un binaire
   existant inconnu pour contourner une erreur d'intégrité.
5. Confirmer l'accès aux poids français avec clonage et l'acceptation de leurs
   conditions Hugging Face. Le premier lancement peut télécharger l'archive
   officielle et des poids. Un jeton de lecture éventuel est saisi uniquement
   dans la console locale masquée, jamais dans une commande, un chat ou un log.
6. Ajouter ensuite la copie du WAV comme indiqué. Ne double-cliquer le CMD
   qu'après ces vérifications. Piper reste sélectionné ; ce paquet ne bascule
   pas ATLAS vers Pocket TTS.

```powershell
$racine = (Get-Location).Path
Get-Content -LiteralPath '.\SHA256SUMS.txt' | ForEach-Object {
    if ($_ -notmatch '^([0-9a-f]{64})  (.+)$') { throw 'Ligne de contrôle invalide' }
    $attendue = $Matches[1]
    $fichier = Join-Path $racine $Matches[2]
    $obtenue = (Get-FileHash -LiteralPath $fichier -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($obtenue -ne $attendue) { throw 'Empreinte différente : ne pas lancer le paquet' }
}
'Empreintes du contenu vérifiées.'
```

Le lanceur renvoie le code Python après la pause. Un code non nul est un échec,
pas une invitation à désactiver les contrôles. Sans le WAV, il refuse de commencer
avant téléchargement ou demande de jeton. Le profil n'est publié qu'après son
contrôle technique de génération hors ligne ; le WAV de contrôle est supprimé.
Ce contrôle ne permet pas à lui seul de juger la ressemblance avec Rachid.

## Sauvegarde et retour arrière

Avant essai : conserver l'archive reçue et son empreinte, l'enregistrement original,
une copie privée de la configuration ATLAS réellement utilisée et l'inventaire
des fichiers moteur/profil/cache HF préexistants. Ne pas placer ces sauvegardes
sur GitHub. Le paquet ne modifie pas la configuration ATLAS ni celle de Piper.

Après échec : lire l'erreur et les catégories de temporaires conservés. Ne pas
relancer en boucle, ne pas remplacer un fichier préexistant et ne pas publier les
sorties privées. Fermer uniquement les processus de cette tentative avant de
réessayer le nettoyage d'un fichier verrouillé.

Pour annuler l'essai : supprimer UNIQUEMENT les fichiers identifiés comme créés
par cet essai, dans le dossier extrait et la destination privée. Ne jamais
supprimer globalement le dossier privé, la référence originale ou le cache HF
partagé. Les poids téléchargés peuvent subsister dans ce cache ; leur suppression
exige l'inventaire préalable et la vérification qu'aucun autre usage n'en dépend.
Piper reste inchangé. Aucune restauration de configuration n'est nécessaire
si elle n'a pas été modifiée manuellement.

## Preuves et limites

Les scripts de ce commit ont été contrôlés sur GitHub Actions Windows : 20 tests
du préparateur et 23 du lanceur, sans échec ni exclusion. Les cas CMD réels
couvrent py -3 et python, les codes 0 et 7, et un paquet incomplet. L'installation
préparatoire du véritable binaire officiel et sa réutilisation ont aussi réussi.
Preuve : https://github.com/Rachid-Coaching-Life/ATLAS/actions/runs/43299561501

L'assemblage du présent ZIP est contrôlé par empreintes et comparaison au commit.
Il n'a pas été installé ni exécuté sur le GTR7. La qualité du WAV personnel, les
ACL et chemins réels, l'accès du compte aux poids de clonage, la ressemblance de
la voix, la latence et une génération personnelle réellement sans Internet
restent NON VÉRIFIÉS. Aucun clonage ni installation personnelle réussi n'est
revendiqué. Les contrôles d'endpoint HF ne remplacent pas une isolation réseau
complète du système pour un futur essai sans Internet.
