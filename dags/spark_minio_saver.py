from datetime import datetime

from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.spark_kubernetes import SparkKubernetesOperator

with DAG(
    dag_id="spark_minio_saver",
    start_date=datetime(2023, 1, 1),
    schedule_interval=None,
    catchup=False,
) as dag:
    submit_spark_job = SparkKubernetesOperator(
        task_id="submit_spark_job",
        application_file="local:///opt/spark/app/spark-minio-saver.jar",
        main_class="com.cawooka.MainExecutor",  # Ensure this is the correct fully qualified name
        kubernetes_conn_id="kubernetes_default",
        namespace="default",
        do_xcom_push=True,
        # --- Crucial for waiting for job completion ---
        # If your Airflow is running inside the same Kubernetes cluster as Spark
        # in_cluster=True,
        # --- End of crucial settings ---
    )
