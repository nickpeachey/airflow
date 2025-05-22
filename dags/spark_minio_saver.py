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
        wait_for_completion=True,
        # If your Airflow is running inside the same Kubernetes cluster as Spark
        # in_cluster=True,
        # --- End of crucial settings ---
        conf={
            "spark.hadoop.fs.s3a.endpoint": "http://minio.default.svc.cluster.local:9000",
            "spark.hadoop.fs.s3a.access.key": "eF8UaaYZ9xhPJha6scs8",
            "spark.hadoop.fs.s3a.secret.key": "fVW9DFwL3V05pDXnsjeVk3S7NANKFrxf",
            "spark.hadoop.fs.s3a.path.style.access": "true",
            "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
            "spark.kubernetes.authenticate.driver.serviceAccountName": "airflow-worker",
            "spark.kubernetes.container.image": "nickpeachey/sparkminiosaver:0.0.3",
            "spark.driver.memory": "512m",
            "spark.executor.memory": "512m",
            "spark.executor.instances": "2",
            "spark.eventLog.enabled": "true",
            "spark.eventLog.dir": "s3a://airflow-logs/spark-events"
        },
    )