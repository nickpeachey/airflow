from datetime import datetime

from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.spark_kubernetes import SparkKubernetesOperator

with DAG(
    dag_id="spark_minio_saver",
    start_date=datetime(2023, 1, 1),
    schedule_interval=None,
    catchup=False,
) as dag:

    submit = SparkKubernetesOperator(
        task_id="submit_spark_job",
        namespace="default",
        application_file="spark-minio.yaml",
        kubernetes_conn_id="kubernetes_default",
        in_cluster=True
)