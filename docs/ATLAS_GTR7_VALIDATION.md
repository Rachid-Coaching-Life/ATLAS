# ATLAS — Procédure d'acceptation sur le mini-PC GTR7

État : **essai matériel non encore réalisé**. Ce document ne constitue pas une preuve d'installation réussie.

## Préconditions

- Utiliser **uniquement** une nouvelle exécution réussie du workflow `ATLAS GTR7 Windows Validation` sur la branche `chatgpt/atlas-installer-safety`, après le correctif de sécurité de l'installateur (PR #16).
- **Ne pas installer** l'artefact antérieur du run `43024138951` : il contient un script de désinstallation et d'auto-suppression que nous avons ensuite corrigé.
- Conserver une sauvegarde des configurations et données personnelles existantes. Ne pas supprimer les anciens dossiers de l'application manuellement.
- Le contrôle de sécurité Windows et la provenance exacte du téléchargement doivent être vérifiés par l'utilisateur avant lancement ; ne pas désactiver SmartScreen ou l'antivirus pour forcer une installation.

## Télécharger et installer

1. Ouvrir le workflow GitHub Actions **réussi** de la branche de correction : `https://github.com/Rachid-Coaching-Life/ATLAS/actions/runs/43026841844` (si ce run échoue, utiliser seulement un **run ultérieur réussi** issu de la même branche corrigée).
2. Sous **Artifacts**, récupérer `ATLAS-Windows`. Décompresser l'archive externe puis `ATLAS-Windows-x64.zip`.
3. Vérifier la présence de `ATLAS-Setup-x64.exe`, lancer l'installateur en prenant note de toute alerte Windows. Vérifier que l'application proposée s'appelle uniquement **ATLAS**.
4. Laisser l'option CUDA désactivée si aucune carte NVIDIA compatible n'est détectée ; ne pas imposer de téléchargement GPU pour les essais vocaux.
5. Lancer ATLAS par le menu Démarrer ou le raccourci Windows, **sans terminal**.

## Tests manuels (noter OK / KO / Non testé)

| Test | Résultat | Observation |
| --- | --- | --- |
| L'installation s'achève sans erreur | Non testé | |
| ATLAS apparaît au menu Démarrer | Non testé | |
| L'application démarre sans console Python | Non testé | |
| L'interface ATLAS et son portrait sont corrects | Non testé | |
| Le panneau d'interaction s'affiche et reste utilisable | Non testé | |
| Microphone détecté, autorisation Windows accordée | Non testé | |
| Reconnaissance de « ATLAS, présente-toi en français » | Non testé | |
| Réponse audible et compréhensible en français | Non testé | |
| « Liste les PDF de mes documents » donne un inventaire en lecture seule | Non testé | |
| « ATLAS, ouvre mon certificat médical » déclenche le bon choix de fichier, sans erreur | Non testé | Ne pas utiliser un document sensible pour les premiers essais ; préférer un PDF de test |
| Une opération d'écriture demandée dans un dossier de test affiche une confirmation avant exécution | Non testé | Ne pas utiliser de documents réels |
| Refuser une action sensible ne modifie aucun fichier | Non testé | |
| Redémarrer ATLAS ne produit pas de processus doublon | Non testé | |
| Les réglages et données de l'ancien logiciel ne sont pas détruits par la mise à niveau | Non testé | |
| La désinstallation ne supprime pas les fichiers non gérés placés dans le dossier d'installation | Non testé | Tester uniquement avec un fichier témoin temporaire et une installation jetable |

## Preuves et blocages

Pour chaque échec, conserver : version Windows, étape, texte exact de l'erreur, capture sans données sensibles, et extrait de journal pertinent. Ne pas envoyer de mots de passe, de tokens, de voix ou de documents personnels.

## Critères de clôture

L'application n'est pas considérée comme prête pour un usage quotidien tant que l'installation, la reconnaissance vocale, la synthèse, les confirmations de sécurité et la conservation des données n'ont pas été validées sur le GTR7. Les échecs unitaires connus de la CI doivent être triés et corrigés selon leur impact, sans masquer les assertions.
