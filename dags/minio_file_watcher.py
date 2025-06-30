import os

from datetime import datetime, timedelta
from airflow import DAG
from airflow.utils.dates import days_ago
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.providers.amazon.aws.hooks.s3 import S3Hook # Import S3Hook
import base64
import hashlib

def delete_minio_file(bucket_name, bucket_key, aws_conn_id):
    """
    Deletes a file from the specified MinIO bucket, handling Content-MD5 if required.
    """
    s3_hook = S3Hook(aws_conn_id=aws_conn_id)
    s3_client = s3_hook.get_conn() # Get the underlying boto3 S3 client

    # Construct the object to delete
    delete_objects_payload = {'Objects': [{'Key': bucket_key}]}

    # MinIO sometimes requires Content-MD5 for DeleteObjects even for single items
    # Calculate the MD5 of the *request body* (the XML payload)
    # Note: Boto3 might handle this automatically in some cases, but explicitly adding
    # it can resolve issues with specific S3-compatible servers like MinIO.
    try:
        # This will convert the Python dict to the XML format that S3 expects
        # for DeleteObjects, then calculate MD5.
        # This is the tricky part, as boto3 handles the XML generation internally.
        # The simplest way to handle this if the direct delete_object() below fails
        # is often to configure MinIO not to require Content-MD5 for delete_objects,
        # but let's try the direct delete_object first.

        # Let's try the delete_object method directly from the boto3 client first,
        # as it's the more direct way to delete a single object and might not
        # require Content-MD5 in the same way as the batch delete_objects.

        s3_client.delete_object(Bucket=bucket_name, Key=bucket_key)
        print(f"File '{bucket_key}' deleted from bucket '{bucket_name}' using direct delete_object.")

    except Exception as e:
        # If delete_object fails, and it's due to Content-MD5,
        # it suggests a very strict MinIO config.
        # The primary reason for the original error was `DeleteObjects`,
        # but `delete_object` should be tried first for single file.
        print(f"Attempt to delete using s3_client.delete_object failed: {e}")
        print("Falling back to s3_hook.delete_objects, which might have the Content-MD5 issue.")

        # If the above still fails, and you're sure it's about Content-MD5 for DeleteObjects,
        # you'd need to manually construct the XML and MD5. This is more advanced.
        # However, the S3Hook's delete_objects method should handle this unless
        # your MinIO is unusually configured.

        # Let's revert to using the S3Hook's delete_objects if the direct boto3 client call fails
        # (though the original error suggests the S3Hook's delete_objects was already failing due to MD5).
        # The root cause is likely the MinIO configuration.
        try:
            s3_hook.delete_objects(bucket=bucket_name, keys=bucket_key)
            print(f"File '{bucket_key}' deleted from bucket '{bucket_name}' using s3_hook.delete_objects.")
        except Exception as inner_e:
            print(f"Error even with s3_hook.delete_objects: {inner_e}")
            raise inner_e # Re-raise the exception if both fail

dag = DAG(
    'minio_file_watcher',
    default_args={'start_date': days_ago(1)},
    description='Prints files in a MinIO bucket',
    schedule_interval=timedelta(minutes=5),
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