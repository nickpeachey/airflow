import os
import boto3
from datetime import datetime, timedelta
from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator

def print_minio_files(**kwargs):
    conn = BaseHook.get_connection('minio_conn')
    minio_endpoint = conn.host
    minio_access_key = conn.login
    minio_secret_key = conn.password
    bucket_name = 'my-minio-bucket'



    s3 = boto3.client(
        's3',
        endpoint_url=http://minio.minio.svc.cluster.local:9000,
        aws_access_key_id=minio_access_key,
        aws_secret_access_key=minio_secret_key,
        region_name='us-east-1',
        config=boto3.session.Config(signature_version='s3v4'),
    )

    response = s3.list_objects_v2(Bucket=bucket_name)
    file_list = []
    if 'Contents' in response:
        for obj in response['Contents']:
            file_list.append(obj['Key'])
    print("Current files in MinIO bucket:")
    if file_list:
        for f in file_list:
            print(f" - {f}")
    else:
        print("(Bucket is empty)")

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2023, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'minio_file_watcher',
    default_args=default_args,
    description='Prints files in a MinIO bucket',
    schedule_interval='@once',
    catchup=False,
    tags=['minio', 'file-watcher'],
)

print_files = PythonOperator(
    task_id='print_minio_files',
    python_callable=print_minio_files,
    provide_context=True,
    dag=dag,
) 