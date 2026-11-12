# ATLAS — Pocket TTS français, pont local expérimental (12 novembre 2026)

## Justification vérifiée
Le moteur retenu est Kyutai Pocket TTS v4.0.1, langue french et voix conditionnée depuis un profil privé préexporté. La documentation officielle et les sources de ce tag exposent les commandes serve --language french --default-voice avec le serveur 127.0.0.1, GET /health et POST /tts avec uniquement le champ text, renvoyant un WAV mono 16 bits.

Sources :
https://github.com/kyutai-labs/pocket-tts/releases
https://github.com/kyutai-labs/pocket-tts/blob/v4.0.1/pocket_tts/main.py
https://github.com/kyutai-labs/pocket-tts/blob/v4.0.1/rust/src/server.rs

Les assets du tag v4.0.1 portent des noms de fichiers 3.3.0 : la version effective du binaire Windows doit être auditée avant son provisionnement. Ne jamais présumer qu'un nom de fichier établit la version binaire.

## Comportement implémenté, mais NON VALIDÉ SUR GTR7
Piper reste le moteur par défaut. Pour sélectionner Pocket TTS de façon réversible, le fichier local de paramètres peut sélectionner tts_engine=pocket et deux variables d'environnement privées doivent pointer vers des fichiers locaux absolus :
- ATLAS_POCKET_TTS_BINARY : exécutable provenant d'une source officielle dont la provenance et la version ont été vérifiées.
- ATLAS_POCKET_TTS_PROFILE : profil local privé .safetensors exporté depuis la référence WAV de Rachid (non inclus au dépôt).

Au démarrage seulement, ATLAS vérifie les deux chemins, démarre l'exécutable dans son propre processus sur un port loopback disponible, demande le modèle french, définit le profil en tant que default-voice et force le client Hugging Face Rust vers une adresse locale inaccessible (HF_ENDPOINT) et configure HF_HUB_OFFLINE. Sans poids français préinstallés, le service échoue au lieu de joindre le dépôt distant. Pas d'installation automatique, pas de création de profil et aucun transfert de WAV privé dans HTTP ou sur GitHub. Les messages d'erreur masquent les chemins privés.

Chaque réponse est envoyée par POST /tts, avec le texte uniquement, sans champ de voix. Le WAV est validé avant lecture audio, le moteur reste propriétaire des callbacks d'activité et du signal de durée, avec suivi d'énergie acoustique pour la bouche. L'arrêt du moteur arrête également le processus local qu'il possède.

Les démarrages concurrents partagent un seul processus. L'arrêt invalide le
démarrage en cours ; un redémarrage après un arrêt terminé crée un nouveau
serveur. Les requêtes de santé refusent les redirections. Le transport de
synthèse utilise directement le loopback, sans proxy ni redirection HTTP.
L'interruption ferme la communication bloquée, y compris avant les en-têtes,
sans arrêter le modèle ; la réponse suivante peut réutiliser le serveur.

Un corps HTTP incomplet, un dépassement de 32 Mio ou un WAV fini tronqué est
refusé. Le WAV en flux du serveur Rust officiel annonce un milliard de trames
dans son en-tête ; sa durée est calculée sur le PCM effectivement reçu. Les
tests utilisent ce format ainsi que des WAV finis synthétiques.

## Limites et conditions avant intégration quotidienne
Les tests CI utilisent des doublures de service, des profils fictifs et des WAV artificiels. Ils ne démontrent ni la fidélité du timbre, ni la vitesse du modèle français sur AMD Ryzen, ni la compatibilité exacte du binaire publié avec le système Windows du GTR7.
Le prototype reçoit le WAV complet avant de commencer à le lire : cette version ne constitue PAS encore la lecture à faible latence promise par le moteur. La durée de génération, les interruptions réseau en cas de blocage et l'expérience réelle exigent une validation dédiée.

D'abord vérifier la CI et les contraintes du binaire, ensuite décider des améliorations de streaming nécessaires avant un déploiement. Aucun essai utilisateur n'est requis pendant cette étape de développement.

Retour arrière : rechoisir tts_engine=piper. Aucune donnée personnelle ni préférence existante ne sont modifiées par cette PR.

## Contrôle officiel de l'exécutable Windows (CI)

Le tag [v4.0.1](https://github.com/kyutai-labs/pocket-tts/releases/tag/v4.0.1) contient l'archive Windows pocket-tts-3.3.0-x86_64-pc-windows-msvc.zip, SHA256 public :

98753041f2e65744b989776f87bccb93f1f574a08afe1890c5427ec94cd6309c

Le workflow Windows télécharge uniquement cet exécutable public, vérifie son empreinte SHA256 et contrôle les sorties --version et serve --help sans télécharger de modèle, sans voix privée et sans modifier le GTR7.

Attention : le tag du dépôt est v4.0.1 mais Cargo et l'archive Windows de ce même tag indiquent 3.3.0. La sortie effective de --version permet de constater la version binaire, pas d'inférer la prise en charge fonctionnelle du modèle français sans essai de synthèse. Le contrôle CLI ne démontre ni clonage ni latence.

Le contrôle de démarrage vérifie aussi la réponse JSON officielle {"status":"healthy"} et non le seul HTTP 200 ; ceci limite les faux positifs si un autre processus local occupe le port sélectionné. Le mécanisme de port dynamique et les conditions de concurrence réelles restent à valider.

## Portée des preuves de fiabilité

Les tests ciblés couvrent des échanges HTTP réels avec un serveur de test sur
loopback, l'annulation pendant l'attente des en-têtes ou du corps, le refus des
redirections, la réponse suivante après interruption et les callbacks d'état
avec une sortie audio factice. Un processus Python synthétique est réellement
démarré, arrêté et redémarré ; il ne charge pas Pocket TTS ni de modèle vocal.
Les contrôles de concurrence et de terminaison forcée utilisent des doublures.
Le workflow Windows inclut ces tests, sans en déduire un succès avant son
exécution.

L'archive officielle Windows a une empreinte épinglée et son code source expose
`french`, `--default-voice` et le protocole WAV utilisé ici. Un contrôle de CLI,
une inspection du binaire ou les tests synthétiques ne prouvent pas qu'il peut
charger les poids français et un profil donné puis produire une voix correcte.
La synthèse française avec l'exécutable officiel Windows, le timbre personnel,
la latence sur Ryzen et l'alignement sur le périphérique audio restent non
validés. Aucun enregistrement ni profil privé n'est nécessaire aux tests.

### Correctif d'interruption Windows, à valider par GitHub Actions

La CI Windows du commit `75ca2d0` montrait encore 5 échecs sur 28, y compris après `shutdown()` et `close()` du socket : le décodage `http.client.HTTPResponse` pouvait rester en lecture bloquante. Le remplacement ciblé utilise un lecteur HTTP/1.1 local borné, avec sondage du socket toutes les 200 ms et décodage `Content-Length`/`Transfer-Encoding: chunked`. Le nouveau contrôle doit passer sous Windows avant toute validation. Aucune bibliothèque supplémentaire, aucun WAV privé dans la CI.
