# Airflow — Setup et credentials GCP

## Pourquoi Airflow dans ce projet

Le poller et le consumer tournent en continu (streaming).
Airflow orchestre la couche de transformation : toutes les 15 minutes,
il vérifie que la donnée est fraîche puis lance `dbt run` + `dbt test`.
Si un test dbt échoue, Airflow logge l'erreur. En production : alerte Slack.

Sans Airflow, il faudrait un cron sans retry, sans monitoring, sans
visibilité sur ce qui a échoué et pourquoi.

## Credentials GCP dans Docker — la solution

Le docker-compose monte le fichier ADC (Application Default Credentials)
depuis ta machine locale dans le container :

```yaml
volumes:
  - ~/.config/gcloud:/home/airflow/.config/gcloud:ro
environment:
  GOOGLE_APPLICATION_CREDENTIALS: /home/airflow/.config/gcloud/application_default_credentials.json
```

Condition préalable sur ta machine hôte :
```bash
gcloud auth application-default login
```

Cette commande crée `~/.config/gcloud/application_default_credentials.json`.
Le container y accède en lecture seule. Aucun fichier JSON à copier manuellement,
aucune variable d'environnement avec un mot de passe en clair.

## Lancer Airflow

```bash
cd airflow/

# Créer le fichier .env avec ton UID et ton project ID
echo "AIRFLOW_UID=$(id -u)" > .env
echo "GCP_PROJECT_ID=" >> .env

# Premier lancement — initialise la base de données Airflow
docker compose up airflow-init

# Lancer les services
docker compose up -d

# Ouvrir l'interface : http://localhost:8080
# Login : admin / admin

# Activer le DAG dans l'interface, puis le déclencher manuellement
# pour le premier test.

# Logs en temps réel du scheduler
docker compose logs -f airflow-scheduler

# Arrêter
docker compose down
```

## Ce que fait le DAG

```
check_source_freshness
        |
        |  Vérifie que raw_flights a des données
        |  de moins de 10 minutes. Si non : FAIL.
        v
dbt_run_staging
        |
        |  dbt run --select staging
        v
dbt_run_marts
        |
        |  dbt run --select marts
        v
dbt_test
        |
        |  dbt test (unique, not_null, accepted_values...)
        v
notify_success ────── (TriggerRule.ALL_SUCCESS)
        
notify_failure ────── (TriggerRule.ONE_FAILED) — se déclenche si
                      n'importe quelle tâche upstream a échoué
```

## Pourquoi `check_source_freshness` en premier

C'est une vérification défensive. Si le poller est tombé et que
`raw_flights` n'a pas été mise à jour depuis 10 minutes, lancer
`dbt run` produirait des marts obsolètes sans aucune alerte.

En déclinant la tâche de freshness en premier, on s'assure que
le reste du pipeline ne tourne que sur de la donnée récente.
C'est l'équivalent de `dbt source freshness` intégré dans l'orchestration.

## En production (ce que tu dirais à Kering)

"En production, je remplacerais le dbt profile monté depuis la machine
locale par un Service Account JSON stocké dans GCP Secret Manager,
injecté dans le container au démarrage. Et j'ajouterais un
SlackWebhookOperator sur la tâche notify_failure pour alerter en temps réel.
La structure du DAG reste identique."
