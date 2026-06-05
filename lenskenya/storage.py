import os
from urllib.parse import quote

from django.conf import settings


MAX_RAW_UPLOAD_BYTES = 30 * 1024 * 1024


def private_raw_bucket_name():
	return getattr(settings, 'AWS_PRIVATE_RAW_BUCKET', 'lenske-private-raw')


def public_preview_bucket_name():
	return getattr(settings, 'AWS_PUBLIC_PREVIEWS_BUCKET', 'lenske-public-previews')


def s3_region_name():
	return getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-1')


def s3_endpoint_url():
	return getattr(settings, 'AWS_S3_ENDPOINT_URL', None) or None


def s3_public_base_url():
	configured = getattr(settings, 'AWS_PUBLIC_PREVIEWS_BASE_URL', '')
	if configured:
		return configured.rstrip('/')

	endpoint_url = s3_endpoint_url()
	bucket = public_preview_bucket_name()
	if endpoint_url:
		return f"{endpoint_url.rstrip('/')}/{bucket}"
	return f"https://{bucket}.s3.{s3_region_name()}.amazonaws.com"


def s3_client():
	try:
		import boto3
	except ImportError as exc:
		raise RuntimeError('boto3 is required for S3 storage. Install requirements.txt first.') from exc

	return boto3.client(
		's3',
		region_name=s3_region_name(),
		endpoint_url=s3_endpoint_url(),
		aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
		aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
	)


def create_raw_upload_post(key, content_type):
	return s3_client().generate_presigned_post(
		Bucket=private_raw_bucket_name(),
		Key=key,
		Fields={'Content-Type': content_type},
		Conditions=[
			{'Content-Type': content_type},
			['content-length-range', 1, MAX_RAW_UPLOAD_BYTES],
		],
		ExpiresIn=getattr(settings, 'AWS_UPLOAD_INTENT_EXPIRES_SECONDS', 600),
	)


def create_raw_download_url(key):
	return s3_client().generate_presigned_url(
		'get_object',
		Params={'Bucket': private_raw_bucket_name(), 'Key': key},
		ExpiresIn=getattr(settings, 'AWS_DOWNLOAD_URL_EXPIRES_SECONDS', 600),
	)


def public_preview_url(key):
	return f"{s3_public_base_url()}/{quote(key, safe='/')}"
