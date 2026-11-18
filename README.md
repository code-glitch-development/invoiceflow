# InvoiceFlow ↗

Application Streamlit en français, créée à partir du concept InvoiceFlow fourni.
Démo académique de financement de factures / reverse factoring, sans transfert d’argent.

## Démarrage local

Prérequis : Python 3.10 ou supérieur.
Décompressez le projet, ouvrez un terminal dans le dossier `invoiceflow`, puis :

```bash
python -m venv .venv
```

Activez l’environnement :

- Windows PowerShell : `.venv\Scripts\Activate.ps1`
- macOS / Linux : `source .venv/bin/activate`

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Ouvrez l’adresse affichée dans le terminal, généralement http://localhost:8501.
Aucune clé API n’est nécessaire.

## Démonstration en 3 minutes

1. Dans **Vue d’ensemble**, explorez les quatre exemples fictifs.
2. Profil **PME**, page **Déposer une facture** : saisissez une nouvelle référence, un SIREN fictif de 9 chiffres, un montant et une échéance future. Choisissez une solidité « Solide » et un historique « Ponctuel ». Cochez les deux contrôles simulés.
3. Profil **Client final**, page **Validation client** : choisissez le client et la facture, cochez la confirmation puis validez. Vous pouvez aussi contester avec un motif.
4. Profil **Investisseur**, page **Financement** : sélectionnez la facture confirmée, réglez commission, recours et couverture, puis simulez le financement.
5. Dans **Portefeuille**, exportez la vue CSV ou la session JSON ; simulez un retard, un litige, une insolvabilité ou un règlement intégral.
6. Le **Simulateur** fonctionne indépendamment du portefeuille et affiche les effets des hypothèses ainsi qu’une estimation de commissions mensuelles et annuelles.

La barre latérale permet de réinitialiser les données. Les exemples utilisent des échéances relatives au jour du lancement.

## Fonctionnement et limites

- Les profils servent à la présentation et ne constituent pas une authentification. Toute personne dans la session peut changer de rôle et de client.
- Données conservées dans `st.session_state` : pas de base de données, aucune synchronisation entre navigateurs, fermeture/reconnexion susceptible de perdre la session. Exportez le JSON pour conserver une trace ; l’import de sauvegarde n’est pas implémenté.
- Dépôt PDF / PNG / JPEG facultatif, 10 Mo maximum : seule l’empreinte est conservée, aucun OCR ni archivage du fichier.
- Détection de doublons limitée à la session : SIREN + référence normalisée, ou empreinte SHA-256 identique du fichier. Ne détecte pas les cessions sur d’autres plateformes, ni toutes les modifications d’une même facture.
- SIREN : contrôle du format uniquement, sans vérification d’existence. Identité, pièces et données de risque sont des déclarations simulées.
- Registre SHA-256 local des métadonnées, sans blockchain, horodatage certifié ni preuve de prestation.
- Score explicable sur 100 : solidité 40/25/5, historique 25/15/0, confirmation 25, pièces 10. Seuil pédagogique ≥ 65, identité et pièces complètes, confirmation client et échéance future obligatoires. Aucune estimation réelle de défaut.
- Financement : commission calculée sur la valeur nominale ; avance = nominal − commission. Aucun intérêt annualisé ou rendement garanti.
- Insolvabilité : indemnité hypothétique = min(avance, nominal × couverture). Capital résiduel = avance − indemnité. Pour 10 000 €, 4 % et 80 %, cela donne 9 600 € avancés, 8 000 € d’indemnité et 1 600 € restant exposés, distincts des 2 000 € de nominal non couverts.
- Le recours est modélisé comme une créance éventuelle sur la PME du résiduel après assurance, dont le recouvrement n’est jamais supposé acquis. Il n’annule pas le risque du financeur. Aucune assurance n’est supposée pour le scénario de contestation ou fraude.
- Modèle volontairement simplifié : pas de franchise, carence, plafond contractuel, recouvrement, coût de financement ou coût d’assurance. Le cas « sans recours » n’est pas présenté comme une couverture universelle.
- Les données fournies sont fictives ; utilisez uniquement des pièces fictives dans ce démonstrateur. Le projet ne fournit ni validation juridique ni service financier réel.

## Déployer sur Streamlit Community Cloud

Placez les fichiers du dossier dans un dépôt GitHub, connectez ce dépôt à Streamlit Community Cloud et sélectionnez `app.py` comme fichier principal (ou `invoiceflow/app.py` si vous conservez le dossier parent). Aucun secret n’est requis. Le déploiement n’est pas réalisé par ce livrable. Chaque session conserve ses données séparément.

## Vérification

```bash
python -m unittest -v
```

Les tests couvrent les calculs, les doublons, les préconditions de financement, la contestation et le cycle jusqu’au règlement. `test_ui.py` vérifie les écrans et le parcours entre profils avec le banc de test Streamlit.

## Fichiers

- `app.py` : interface et parcours Streamlit.
- `engine.py` : règles, calculs et jeu de données.
- `requirements.txt` : dépendances.
- `.streamlit/config.toml` : thème et limite d’envoi.
- `test_engine.py`, `test_ui.py` : tests automatisés.
