# ATLAS

**ATLAS** est un assistant personnel local, francophone, destiné en priorité au mini-PC GTR7 sous Windows. Le dépôt de développement est [Rachid-Coaching-Life/ATLAS](https://github.com/Rachid-Coaching-Life/ATLAS).

## État du projet

ATLAS est en développement. **Il n'existe pas encore de version Windows entièrement validée pour le GTR7.** Les correctifs de sécurité, l'interface de bureau PyQt6, le démarrage vocal et les tests multi-plateformes font l'objet de validations progressives.

## Objectif de livraison

L'application finale doit pouvoir être installée et démarrée depuis Windows, avec une interface ATLAS, des interactions vocales en français, des fonctions locales et des confirmations explicites avant les actions sensibles, sans terminal requis pour l'usage quotidien.

## Développement

- Branche de référence : `develop-atlas`. Les changements sont préparés sur des branches dédiées et examinés en pull requests.
- Python 3.11 ou ultérieur est nécessaire au développement depuis les sources.
- Les dépendances et les commandes de démarrage restent celles du dépôt pendant la migration technique. Ne pas renommer manuellement les packages ou chemins d'import avant leur adaptation et leur validation.
- Les tests Linux CI ne remplacent pas les essais sur le GTR7 Windows.

## Migration de l'identité

**ATLAS est le nom unique du produit.** Les anciens identifiants internes, variables et chemins encore présents dans le code sont en cours de migration contrôlée. Les renommages doivent préserver les imports, la configuration utilisateur, les données locales, les exécutables et l'installation Windows. La migration n'est terminée qu'après tests et vérification de l'absence de références héritées dans les interfaces et les livrables.

## Licences

Consulter les fichiers de licence et les notices de tiers inclus dans ce dépôt. Le changement de nom du produit ne supprime aucune obligation d'attribution des composants d'origine ou tiers.
