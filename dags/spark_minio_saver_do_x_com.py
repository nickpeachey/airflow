import json
import os
from datetime import datetime
from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.task_group import TaskGroup
from airflow.providers.cncf.kubernetes.operators.spark_kubernetes import SparkKubernetesOperator
from airflow.providers.cncf.kubernetes.sensors.spark_kubernetes import SparkKubernetesSensor


def generate_spark_minio_config(**kwargs):
    """
    Retrieves Minio connection details from Airflow and generates a
    SparkApplication spec file path for SparkKubernetesOperator.
    """
    conn = BaseHook.get_connection('minio_conn')
    extras = json.loads(conn.extra) if conn.extra else {}
    endpoint_url = extras.get('endpoint_url')

    minio_access_key = conn.login
    minio_secret_key = conn.password

    execution_timestamp = kwargs.get(
        'ts_nodash',
        datetime.now().strftime("%Y%m%dT%H%M%S")
    )
    spark_app_name = f"scala-spark-job-{execution_timestamp}"

    spark_application_config = {
        "apiVersion": "sparkoperator.k8s.io/v1beta2",
        "kind": "SparkApplication",
        "metadata": {
            "name": spark_app_name,
            "namespace": "default",
        },
        "spec": {
            "type": "Scala",
            "mode": "cluster",
            "image": "nickpeachey/sparkminiosaver:4.0.5",
            "imagePullPolicy": "Always",
            "mainClass": "com.cawooka.MainExecutor",
            "mainApplicationFile": "local:///opt/spark/jars/spark-debug-app.jar",
            "sparkConf": {
                "spark.hadoop.fs.s3a.endpoint": endpoint_url,
                "spark.hadoop.fs.s3a.access.key": minio_access_key,
                "spark.hadoop.fs.s3a.secret.key": minio_secret_key,
                "spark.hadoop.fs.s3a.path.style.access": "true",
                "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
                "spark.hadoop.fs.s3a.aws.credentials.provider": "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
            },
            "driver": {
                "cores": 1,
                "memory": "1g",
                "serviceAccount": "spark",
                "labels": {},
            },
            "executor": {
                "cores": 1,
                "instances": 1,
                "memory": "1g",
            },
            "restartPolicy": {
                "type": "Never"
            }
        },
    }

    # Save to file
    file_path = f"/tmp/spark_app_{execution_timestamp}.json"
    with open(file_path, "w") as f:
        json.dump(spark_application_config, f)

    ti = kwargs['ti']
