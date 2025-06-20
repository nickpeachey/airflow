from datetime import datetime
from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.spark_kubernetes import SparkKubernetesOperator
from airflow.providers.cncf.kubernetes.sensors.spark_kubernetes import SparkKubernetesSensor

with DAG(
    dag_id="spark_minio_saver-copy",
    start_date=datetime(2023, 1, 1),
    schedule_interval=None,
    catchup=False,
) as dag:
    submit_spark_job = SparkKubernetesOperator(
        # Do NOT set do_xcom_push=True
        do_xcom_push=False,  # Or remove the line entirely
        task_id="submit_scala_job_minio-copy",
        namespace="default",
        application_file="spark-minio-copy.yaml",
        kubernetes_conn_id="kubernetes_default",
        in_cluster=True,
    )

    # Example: A downstream task that depends on the Spark job's completion
    # downstream_task = ...

    submit_spark_job  # >> downstream_task
