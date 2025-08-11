import json
from datetime import datetime
from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.task_group import TaskGroup
from airflow.models.xcom_arg import XComArg
from airflow.providers.cncf.kubernetes.operators.spark_kubernetes import SparkKubernetesOperator
from airflow.providers.cncf.kubernetes.sensors.spark_kubernetes import SparkKubernetesSensor


def generate_spark_minio_config(**kwargs):
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

    ti = kwargs['ti']
    ti.xcom_push(key='spark_app_config_xcom', value=spark_application_config)
    ti.xcom_push(key='spark_app_name_xcom', value=spark_app_name)


with DAG(
    dag_id="spark_minio_saver_do_x_com",
    start_date=datetime(2023, 1, 1),
    schedule=None,
    catchup=False,
    tags=['spark', 'kubernetes', 'minio', 'connections'],
) as dag:

    start = EmptyOperator(task_id='start')

    with TaskGroup("LocalStackJob", tooltip="Localstack Job") as localstack_job:

        generate_spark_config_task = PythonOperator(
            task_id='generate_spark_minio_config_task_spark_minio_saver_do_x_com',
            python_callable=generate_spark_minio_config,
        )

        submit_spark_job = SparkKubernetesOperator(
            task_id="submit_scala_job_minio_spark_minio_saver_do_x_com",
            do_xcom_push=True,
            namespace="default",
            template_body=XComArg(generate_spark_config_task, key='spark_app_config_xcom'),
            kubernetes_conn_id="kubernetes_default",
            in_cluster=True,
        )

        monitor_job = SparkKubernetesSensor(
            task_id="monitor_spark_job_minio_spark_minio_saver_do_x_com",
            application_name=XComArg(generate_spark_config_task, key='spark_app_name_xcom'),
            namespace="default",
            kubernetes_conn_id="kubernetes_default",
            do_xcom_push=True,
        )

        generate_spark_config_task >> submit_spark_job >> monitor_job

    start >> localstack_job
