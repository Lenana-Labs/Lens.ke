from botocore.exceptions import ClientError
from django.core.management.base import BaseCommand

from lenskenya.storage import private_raw_bucket_name, public_preview_bucket_name, s3_client, s3_region_name


class Command(BaseCommand):
	help = 'Create the Lens.ke private raw and public preview buckets if they do not exist.'

	def handle(self, *args, **options):
		client = s3_client()
		for bucket_name, is_public in (
			(private_raw_bucket_name(), False),
			(public_preview_bucket_name(), True),
		):
			self._ensure_bucket(client, bucket_name)
			if is_public:
				self._ensure_public_read_policy(client, bucket_name)
			self.stdout.write(self.style.SUCCESS(f'Bucket ready: {bucket_name}'))

	def _ensure_bucket(self, client, bucket_name):
		try:
			client.head_bucket(Bucket=bucket_name)
			return
		except ClientError as exc:
			error_code = exc.response.get('Error', {}).get('Code')
			if error_code not in {'404', 'NoSuchBucket', 'NotFound'}:
				raise

		region = s3_region_name()
		create_kwargs = {'Bucket': bucket_name}
		if region != 'us-east-1':
			create_kwargs['CreateBucketConfiguration'] = {'LocationConstraint': region}
		client.create_bucket(**create_kwargs)

	def _ensure_public_read_policy(self, client, bucket_name):
		policy = {
			'Version': '2012-10-17',
			'Statement': [
				{
					'Sid': 'PublicPreviewRead',
					'Effect': 'Allow',
					'Principal': '*',
					'Action': ['s3:GetObject'],
					'Resource': [f'arn:aws:s3:::{bucket_name}/*'],
				}
			],
		}
		try:
			import json

			client.put_public_access_block(
				Bucket=bucket_name,
				PublicAccessBlockConfiguration={
					'BlockPublicAcls': False,
					'IgnorePublicAcls': False,
					'BlockPublicPolicy': False,
					'RestrictPublicBuckets': False,
				},
			)
			client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))
		except ClientError as exc:
			self.stderr.write(self.style.WARNING(f'Could not apply public policy to {bucket_name}: {exc}'))
