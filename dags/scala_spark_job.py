from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.spark_kubernetes import SparkKubernetesOperator
from datetime import datetime

with DAG(
    dag_id="scala_spark_job",
    start_date=datetime(2023, 1, 1),
    schedule_interval=None,
    catchup=False,
) as dag:

    submit = SparkKubernetesOperator(
        task_id="submit_scala_job",
        namespace="default",
        application_file="spark-job.yaml",
        kubernetes_conn_id="kubernetes_default",
        in_cluster=True
    )
