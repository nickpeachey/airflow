import os

from datetime import datetime, timedelta
from airflow import DAG
from airflow.utils.dates import days_ago
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.providers.amazon.aws.hooks.s3 import S3Hook # Import S3Hook


def delete_minio_file(bucket_name, bucket_key, aws_conn_id):
    """
    Deletes a file from the specified MinIO bucket.
    """
    s3_hook = S3Hook(aws_conn_id=aws_conn_id)
    # Use delete_key for single file deletion
    s3_hook.delete_key(key=bucket_key, bucket_name=bucket_name)
    print(f"File '{bucket_key}' deleted from bucket '{bucket_name}'.")


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
    bucket_key='sample.csv', # Replace with your MinIO bucket name # Replace with the path to the file you want to watch
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

delete_file_from_minio = PythonOperator(
    task_id='delete_file_from_minio',
    python_callable=delete_minio_file,
    op_kwargs={
        'bucket_name': 'my-minio-bucket',
        'bucket_key': 'sample.csv',
        'aws_conn_id': 'minio_conn'
    },
    dag=dag,
)


wait_for_file >> print_success_message >> delete_file_from_minio