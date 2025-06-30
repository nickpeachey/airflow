import os

from datetime import datetime, timedelta
from airflow import DAG
from airflow.utils.dates import days_ago
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor


dag = DAG(
    'minio_file_watcher',
    default_args={'start_date': days_ago(1)},
    description='Prints files in a MinIO bucket',
    schedule_interval='@once',
    catchup=False,
    tags=['minio', 'file-watcher'],
)

wait_for_file = S3KeySensor(
    task_id='wait_for_file',
    bucket_name='my-minio-bucket',
    bucket_key='', # Replace with your MinIO bucket name # Replace with the path to the file you want to watch
    aws_conn_id='minio_conn',  # Ensure you have a connection named 'minio_conn' configured in Airflow
    wildcard_match=True,
    timeout=600,  # Wait for up to 10 minutes
    poke_interval=30,  # Check every 30 seconds
    dag=dag,
)

print_success_message = PythonOperator(
    task_id='print_success_message',
    python_callable=lambda: print("File detected in MinIO bucket!"),
    dag=dag,
)

wait_for_file >> print_success_message