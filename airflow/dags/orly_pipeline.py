import os
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator
from airflow.utils.trigger_rule import TriggerRule

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
DBT_DIR    = "/opt/airflow/dbt"

default_args = {
    "owner":                     "orly-live",
    "retries":                   2,
    "retry_delay":               timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "email_on_failure":          False,
}

@dag(
    dag_id="orly_live_pipeline",
    description="Orchestrates dbt runs and data quality checks for Orly Live",
    schedule="*/15 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["orly-live", "bigquery", "dbt"],
)
def orly_live_pipeline():

    @task(task_id="check_source_freshness")
    def check_freshness():
        from google.cloud import bigquery
        client = bigquery.Client(project=PROJECT_ID)

        query = """
            SELECT TIMESTAMP_DIFF(
                CURRENT_TIMESTAMP(),
                MAX(snapshot_time),
                MINUTE
            ) AS minutes_old
            FROM `{project}.paris_orly.raw_flights`
        """.format(project=PROJECT_ID)

        rows = list(client.query(query).result())
        minutes_old = rows[0].minutes_old if rows else 9999

        if minutes_old is None:
            raise ValueError("raw_flights is empty — poller may not be running")
        if minutes_old > 10:
            raise ValueError(
                "raw_flights last updated {} min ago — consumer may be down".format(minutes_old)
            )

        print("Source freshness OK — last row {} minutes ago".format(minutes_old))
        return {"minutes_old": int(minutes_old)}

    dbt_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command=(
            "cd {d} && dbt run --select staging "
            "--profiles-dir /home/airflow/.dbt --no-partial-parse".format(d=DBT_DIR)
        ),
        execution_timeout=timedelta(minutes=10),
    )

    dbt_marts = BashOperator(
        task_id="dbt_run_marts",
        bash_command=(
            "cd {d} && dbt run --select marts "
            "--profiles-dir /home/airflow/.dbt --no-partial-parse".format(d=DBT_DIR)
        ),
        execution_timeout=timedelta(minutes=10),
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=(
            "cd {d} && dbt test --profiles-dir /home/airflow/.dbt".format(d=DBT_DIR)
        ),
        execution_timeout=timedelta(minutes=10),
    )

    @task(task_id="notify_success", trigger_rule=TriggerRule.ALL_SUCCESS)
    def notify_success(freshness):
        print("Pipeline OK — source {} min old — all dbt tests passed".format(
            freshness.get("minutes_old")
        ))

    @task(task_id="notify_failure", trigger_rule=TriggerRule.ONE_FAILED)
    def notify_failure():
        print("Pipeline FAILED — check logs above")

    freshness = check_freshness()
    freshness >> dbt_staging >> dbt_marts >> dbt_test
    notify_success(freshness)
    dbt_test >> notify_failure()


orly_live_pipeline()
