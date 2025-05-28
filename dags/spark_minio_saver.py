import os
from datetime import datetime

from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator
# Import necessary operators for Spark on Kubernetes
from airflow.providers.cncf.kubernetes.operators.spark_kubernetes import SparkKubernetesOperator
from airflow.providers.cncf.kubernetes.sensors.spark_kubernetes import SparkKubernetesSensor
from jinja2 import Template # Still useful if you prefer templating YAML strings, but we'll use a dict directly

# Define your Airflow Connection ID for MinIO
# Make sure you have a connection named 'minio_conn' configured in Airflow
# For example, a S3 connection with:
# Conn Id: minio_conn
# Conn Type: S3
# Host: http://minio-service:9000 (or your MinIO endpoint)
# Login: your_access_key
# Password: your_secret_key
# Extra: {"endpoint_url": "http://minio-service:9000", "region_name": "us-east-1", "s3_url_style": "path"} # Optional, but good for S3 type

def generate_spark_minio_config(**kwargs):
    """
    Retrieves Minio connection details from Airflow and generates a
    SparkApplication Kubernetes resource dictionary.
    """
    try:
        # 1. Get the Airflow Connection for MinIO
        conn = BaseHook.get_connection('minio_conn')

        # Extract relevant properties for MinIO
        # For S3 type connection, host is typically the endpoint, login is access key, password is secret key
        minio_host = conn.host
        minio_access_key = conn.login
        minio_secret_key = conn.password

        # MinIO is often accessed via HTTP, ensure the endpoint is correct
        # You might need to parse `conn.host` or use `conn.extra_dejson` for a more robust endpoint
        # For simplicity, assuming conn.host already contains the full endpoint like "http://minio-service:9000"
        # If your host is just "minio-service", you might need to append the port.
        minio_endpoint = minio_host # Assuming host includes protocol and port, e.g., "http://minio-service:9000"
        if not (minio_endpoint.startswith("http://") or minio_endpoint.startswith("https://")):
             # Default to http and port 9000 if not specified in host
            minio_endpoint = f"http://{minio_endpoint}:9000"


        print(f"Retrieved MinIO connection details for {conn.conn_id}:")
        print(f"  Endpoint: {minio_endpoint}")
        print(f"  Access Key: {minio_access_key}")
        # print(f"  Secret Key: {minio_secret_key}") # Avoid printing sensitive info in logs

        # 2. Define the SparkApplication Kubernetes resource as a Python dictionary
        # This dictionary will be passed directly to the SparkKubernetesOperator
        spark_app_name = f"scala-spark-job-{kwargs['ts_nodash']}" # Dynamic name for the Spark Application

        spark_application_config = {
            "apiVersion": "sparkoperator.k8s.io/v1beta2",
            "kind": "SparkApplication",
            "metadata": {
                "name": spark_app_name,
                "namespace": "default", # Or your desired Kubernetes namespace
            },
            "spec": {
                "type": "Scala",
                "mode": "cluster",
                "image": "apache/spark:3.3.0", # IMPORTANT: Replace with your actual Spark image (e.g., with Hadoop S3A support)
                "imagePullPolicy": "Always",
                "mainClass": "com.example.SparkMinioSaver", # IMPORTANT: Replace with your Scala main class
                "mainApplicationFile": "local:///opt/spark/jars/your-spark-app.jar", # IMPORTANT: Path to your JAR inside the Spark image
                "sparkConf": {
                    # Configure Spark to use S3A for MinIO
                    "spark.hadoop.fs.s3a.endpoint": minio_endpoint,
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
                    "labels": {}, # ADDED: Empty labels dictionary to prevent KeyError
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

        # 3. Push the generated dictionary and application name to XCom
        kwargs['ti'].xcom_push(key='spark_app_config', value=spark_application_config)
        kwargs['ti'].xcom_push(key='spark_app_name', value=spark_app_name)

    except Exception as e:
        print(f"Error generating SparkApplication config: {e}")
        raise # Re-raise the exception to fail the task if something goes wrong

# Your DAG definition
with DAG(
    dag_id="spark_minio_saver",
    start_date=datetime(2023, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=['spark', 'kubernetes', 'minio', 'connections'],
) as dag:
    # Task to generate the Spark Application configuration with MinIO details
    generate_spark_config_task = PythonOperator(
        task_id='generate_spark_minio_config_task',
        python_callable=generate_spark_minio_config,
        provide_context=True, # Required to access task instance (ti) for XComs and ts_nodash
    )

    # Task to submit the Spark job to Kubernetes
    submit_spark_job = SparkKubernetesOperator(
        task_id="submit_scala_job_minio",
        namespace="default",
        # Pass the dynamically generated SparkApplication dictionary from XCom
        application_file="{{ task_instance.xcom_pull(task_ids='generate_spark_minio_config_task', key='spark_app_config') }}",
        kubernetes_conn_id="kubernetes_default",
        in_cluster=True,
        # The SparkKubernetesOperator will automatically set the application_name based on the metadata.name in the provided config
    )

    # Task to wait for the Spark job to complete
    wait_for_spark_job = SparkKubernetesSensor(
        task_id="wait_for_spark_job",
        namespace="default",
        # Pull the dynamically generated Spark Application name from XCom
        application_name="{{ task_instance.xcom_pull(task_ids='generate_spark_minio_config_task', key='spark_app_name') }}",
        kubernetes_conn_id="kubernetes_default",
        poke_interval=10,
        timeout=3600,
    )

    # Define the task dependencies
    generate_spark_config_task >> submit_spark_job >> wait_for_spark_job