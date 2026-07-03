# WikiQuiz Live

Jeu de quiz en direct : le serveur pioche un article Wikipédia aléatoire
toutes les 15 secondes, en cache le titre dans l'extrait, et les joueurs
connectés doivent deviner de quel article il s'agit parmi 4 choix. Plus tu
réponds vite, plus tu marques de points. Classement en direct pour tout le monde.

## 🚀 Lancer en local

```bash
pip install -r requirements.txt
python app.py
```

Ouvre http://localhost:5000, entre un prénom, et attends la prochaine question.
Ouvre plusieurs onglets/navigateurs pour tester à plusieurs.

## 🌍 Déployer sur Render.com

1. Pousse ce dossier sur un repo GitHub
2. Sur Render : **New → Web Service**, connecte le repo
3. Build command : `pip install -r requirements.txt`
4. Start command : laisse vide (le `Procfile` est détecté automatiquement)
5. Aucune variable d'environnement obligatoire (le jeu est public, pas de mot de passe)
   — optionnel : `WIKI_LANG` pour changer la langue Wikipédia (ex: `en`, `es`)
6. Clique sur "Create Web Service"

## ⚙️ Comment ça marche

- Une seule partie tourne en continu sur le serveur (pas de salons séparés)
- Les scores sont gardés en mémoire et associés au prénom choisi — si tu
  fermes l'onglet et reviens avec le même prénom, ton score est conservé
  (tant que le serveur n'a pas redémarré)
- `ROUND_DURATION` (15s) et `REVEAL_DURATION` (6s) sont réglables en haut de `app.py`
- Les distracteurs (mauvaises réponses) sont d'autres titres Wikipédia aléatoires

## ⚠️ Limites à connaître

- **Pas de base de données** : si le serveur redémarre (redéploiement, plan
  gratuit qui se réveille), les scores repartent à zéro
- Le plan gratuit Render s'endort après inactivité (~50s de réveil au premier accès)
- Les extraits Wikipédia varient en qualité ; certains articles très courts
  ou ambigus sont filtrés mais quelques questions faciles/étranges peuvent passer
