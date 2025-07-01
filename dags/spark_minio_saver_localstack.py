import os
from airflow.sensors.time_delta import TimeDeltaSensor
from datetime import datetime, timedelta
import json
from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.cncf.kubernetes.operators.spark_kubernetes import SparkKubernetesOperator
from airflow.providers.cncf.kubernetes.sensors.spark_kubernetes import SparkKubernetesSensor

def generate_spark_minio_config(**kwargs):
    """
    Retrieves Minio connection details from Airflow and generates a
    SparkApplication Kubernetes resource dictionary.
    """
    # Initialize variables to None, in case of early exit or error
    spark_app_name = None
    spark_application_config = None

    try:
        # 1. Get the Airflow Connection for MinIO
        # Ensure you have an Airflow Connection named 'minio_conn' configured.
        # Recommended:
        # Conn Id: minio_conn
        # Conn Type: S3
        # Host: http://minio-service.minio.svc.cluster.local:9000 (or your actual MinIO endpoint)
        # Login: your_minio_access_key
        # Password: your_minio_secret_key
        # Extra: {"endpoint_url": "http://minio-service.minio.svc.cluster.local:9000", "region_name": "us-east-1", "s3_url_style": "path"}
        conn = BaseHook.get_connection('minio_conn')
        if conn.extra:
            extras = json.loads(conn.extra)
        
        # Now you can access the 'endpoint_url'
            endpoint_url = extras.get('endpoint_url')
        
        if endpoint_url:
            print(f"MinIO Endpoint URL blahb: {endpoint_url}")
        else:
            print("'endpoint_url' not found in the 'extras' of 'minio_conn'.")


        minio_host = conn.host
        minio_access_key = conn.login
        minio_secret_key = conn.password
        print(f"Retrieved MinIO connection details for {conn}:")
        print(conn)

        # Ensure the MinIO endpoint is a full URL (http/https + host + port)
        # print(f"  Secret Key: {minio_secret_key}") # Avoid printing sensitive info in logs

        # Ensure ts_nodash is available, provide a fallback if not (e.g., during DAG parsing)
        # This makes the spark_app_name more robust
        execution_timestamp = kwargs.get('ts_nodash', datetime.now().strftime("%Y%m%dT%H%M%S"))
        spark_app_name = f"scala-spark-job-{execution_timestamp}" # Dynamic name for the Spark Application

        # 2. Define the SparkApplication Kubernetes resource as a Python dictionary
        # This dictionary will be passed directly to the SparkKubernetesOperator
        spark_application_config = {
            "apiVersion": "sparkoperator.k8s.io/v1beta2",
            "kind": "SparkApplication",
            "metadata": {
                "name": spark_app_name,
                "namespace": "default", # Or your desired Kubernetes namespace for Spark jobs
            },
            "spec": {
                "type": "Scala",
                "mode": "cluster",
                "image": "nickpeachey/sparkminiosaver:4.0.5", # IMPORTANT: Replace with your actual Spark image (e.g., with Hadoop S3A support)
                "imagePullPolicy": "Always",
                "mainClass": "com.cawooka.MainExecutor", # IMPORTANT: Replace with your Scala main class
                "mainApplicationFile": "local:///opt/spark/jars/spark-debug-app.jar", # IMPORTANT: Path to your JAR inside the Spark image
                "sparkConf": {
                    # Configure Spark to use S3A for MinIO
                    # Use the dynamically retrieved endpoint here
                    "spark.hadoop.fs.s3a.endpoint": endpoint_url,
                    "spark.hadoop.fs.s3a.access.key": minio_access_key,
                    "spark.hadoop.fs.s3a.secret.key": minio_secret_key,
                    "spark.hadoop.fs.s3a.path.style.access": "true", # Essential for MinIO
                    "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
                    "spark.hadoop.fs.s3a.aws.credentials.provider": "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
                },
                "driver": {
                    "cores": 1,
                    "memory": "1g",
                    "serviceAccount": "spark", # IMPORTANT: Your Kubernetes service account for Spark
                    "labels": {}, # Ensure this is present to avoid potential KeyError from operator
                },
                "executor": {
                    "cores": 1,
                    "instances": 1,
                    "memory": "1g",
                },
                "restartPolicy": {
                    "type": "Never" # Or OnFailure, Always
                }
            },
        }

        print(f"Generated SparkApplication config for name: {spark_app_name}")

    except Exception as e:
        print(f"Error generating SparkApplication config: {e}")
        # Re-raise the exception to fail the task if something goes wrong.
        # This is crucial so that downstream tasks don't run with invalid XComs.
        raise
    finally:
        # Push XComs only if the values were successfully generated
        # This helps prevent pushing 'None' if an error occurred earlier in the try block
        if spark_application_config is not None:
            kwargs['ti'].xcom_push(key='spark_app_config', value=spark_application_config)
        if spark_app_name is not None:
            kwargs['ti'].xcom_push(key='spark_app_name', value=spark_app_name)


# Your DAG definition
with DAG(
    dag_id="spark_minio_saver_with_localstack",
    start_date=datetime(2023, 1, 1),
    schedule=None,
    catchup=False,
    tags=['spark', 'kubernetes', 'minio', 'connections'],
) as dag:
    # Task to generate the Spark Application configuration with MinIO details
    generate_spark_config_task = PythonOperator(
        task_id='generate_spark_minio_config_task',
        python_callable=generate_spark_minio_config,
    )

    # Task to submit the Spark job to Kubernetes
    submit_spark_job = SparkKubernetesOperator(
        task_id="submit_scala_job_minio",
        namespace="default", # Must match the namespace in spark_application_config metadata
        # Pass the dynamically generated SparkApplication dictionary from XCom
        application_file="{{ task_instance.xcom_pull(task_ids='generate_spark_minio_config_task', key='spark_app_config') }}",
        kubernetes_conn_id="kubernetes_default", # Ensure this connection exists and is valid
        in_cluster=True, # Set to True if Airflow is running inside the Kubernetes cluster
        # The SparkKubernetesOperator will automatically set the application_name based on the metadata.name
        # in the provided application_file dictionary.
    )

      # Task to monitor the Spark job completion
    # Task to monitor the Spark job completion
    # Task to monitor the Spark job completion
    # Task to monitor the Spark job completion



    # Define the task dependencies
    generate_spark_config_task >> submit_spark_job