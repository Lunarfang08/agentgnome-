import boto3
from agentgenome.config import Settings
from botocore.exceptions import ClientError

s = Settings()
if s.profile != "dev":
    raise RuntimeError("Development setup only")
client = boto3.client(
    "s3",
    endpoint_url=s.s3_endpoint,
    aws_access_key_id=s.s3_access_key.get_secret_value(),
    aws_secret_access_key=s.s3_secret_key.get_secret_value(),
)
try:
    client.head_bucket(Bucket=s.s3_bucket)
except ClientError as exc:
    if exc.response["Error"]["Code"] not in {"404", "NoSuchBucket"}:
        raise
    client.create_bucket(Bucket=s.s3_bucket)
