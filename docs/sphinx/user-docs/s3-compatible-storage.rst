S3 compatible storage with Ray Train examples
=============================================

Some of our distributed training examples require an external storage
solution so that all nodes can access the same data. The following are
examples for configuring S3 or Minio storage for your Ray Train script
or interactive session.

S3 Bucket
---------

In your Python Script add the following environment variables:

.. code:: python

   os.environ["AWS_ACCESS_KEY_ID"] = "XXXXXXXX"
   os.environ["AWS_SECRET_ACCESS_KEY"] = "XXXXXXXX"
   os.environ["AWS_DEFAULT_REGION"] = "XXXXXXXX"

Alternatively you can specify these variables in your runtime
environment on Job Submission.

.. code:: python

   submission_id = client.submit_job(
       entrypoint=...,
       runtime_env={
           "env_vars": {
               "AWS_ACCESS_KEY_ID": os.environ.get('AWS_ACCESS_KEY_ID'),
               "AWS_SECRET_ACCESS_KEY": os.environ.get('AWS_SECRET_ACCESS_KEY'),
               "AWS_DEFAULT_REGION": os.environ.get('AWS_DEFAULT_REGION')
           },
       }
   )

In your Trainer configuration you can specify a ``run_config`` which
will utilise your external storage.

.. code:: python

   trainer = TorchTrainer(
       train_func_distributed,
       scaling_config=scaling_config,
       run_config = ray.train.RunConfig(storage_path="s3://BUCKET_NAME/SUB_PATH/", name="unique_run_name")
   )

To learn more about Amazon S3 Storage you can find information
`here <https://docs.aws.amazon.com/AmazonS3/latest/userguide/creating-bucket.html>`__.

Minio Bucket
------------

In your Python Script add the following function for configuring your
run_config:

.. code:: python

   import s3fs
   import pyarrow

   def get_minio_run_config():
      s3_fs = s3fs.S3FileSystem(
          key = os.getenv('MINIO_ACCESS_KEY', "XXXXX"),
          secret = os.getenv('MINIO_SECRET_ACCESS_KEY', "XXXXX"),
          endpoint_url = os.getenv('MINIO_URL', "XXXXX")
      )
      custom_fs = pyarrow.fs.PyFileSystem(pyarrow.fs.FSSpecHandler(s3_fs))
      run_config = ray.train.RunConfig(storage_path='training', storage_filesystem=custom_fs)
      return run_config

You can update the ``run_config`` to further suit your needs above.
Lastly the new ``run_config`` must be added to the Trainer:

.. code:: python

   trainer = TorchTrainer(
       train_func_distributed,
       scaling_config=scaling_config,
       run_config = get_minio_run_config()
   )

To find more information on creating a Minio Bucket compatible with
RHOAI you can refer to this
`documentation <https://ai-on-openshift.io/tools-and-applications/minio/minio/>`__.
Note: You must have ``sf3s`` and ``pyarrow`` installed in your
environment for this method.
