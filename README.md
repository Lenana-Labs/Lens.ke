# Lens.ke Backend

Lens.ke is a Django backend for a Kenyan photo marketplace. It lets contributors upload high-resolution images, generates protected watermarked previews asynchronously, exposes a searchable public catalog, and issues secure download links for licensed or free images.

The backend is deployed on DigitalOcean App Platform with a web service and a Celery worker.

## System Design

### Functional Requirements

- Contributors can upload high-resolution photos and track upload/earnings activity.
- Buyers can browse the catalog, view watermarked previews, and download original images after authorization or payment.
- The platform applies watermarks, stores protected originals separately from public previews, and records revenue splits.

### Non-Functional Requirements

- Low-latency browsing for mobile users on 3G/4G networks.
- Strict IP protection: original high-resolution files must not be publicly accessible.
- Strong transaction consistency for payments, licenses, and contributor payouts.

### Capacity Estimate

- 1,000 contributors uploading 10 images each month.
- About 10,000 new images per month.
- Average original image size: 15 MB.
- Original storage growth: about 150 GB per month.
- Watermarked preview target: about 150 KB per image.
- Preview storage growth: about 1.5 GB per month.
- Expected workload is read-heavy, approximately 100 reads per write.

## Architecture

```text
Client / Frontend
    |
    | HTTPS API requests
    v
DigitalOcean App Platform Web Service
    |
    | Django + DRF API
    v
PostgreSQL

Contributor Upload Flow:

Contributor -> Django API -> Presigned S3/Spaces upload -> Private raw bucket
             -> Finalize endpoint -> Redis queue -> Celery worker
             -> Pillow processing -> Public preview bucket -> PostgreSQL status update
```

### Runtime Components

- **Client tier**: optimized for mobile browsing; CDN such as Cloudflare can sit in front of API/static assets.
- **API tier**: Django REST-style endpoints for authentication, catalog browsing, contributor uploads, profiles, and secure downloads.
- **Ingestion pipeline**: presigned upload intent, metadata finalization, image processing queue, watermarking, compression, and preview publishing.
- **Catalog service**: photo listing, filtering, search by tags, county filters, popularity sorting, and detail lookup.
- **Payment/licensing foundation**: transaction, license, and revenue split models are present. Payment gateway webhook integration is a planned extension point.
- **Storage**: original files are stored in a private S3-compatible bucket; watermarked WebP previews are stored in a public previews bucket.
- **Worker**: Celery consumes Redis messages and processes images with Pillow.
- **Database**: PostgreSQL stores users, photos, transactions, licenses, and refresh tokens.

## Tech Stack

- Python
- Django 6
- Django REST Framework
- drf-spectacular for OpenAPI/Swagger docs
- PostgreSQL
- Redis
- Celery
- Pillow
- boto3 for S3/DigitalOcean Spaces
- Gunicorn
- DigitalOcean App Platform

## Data Model

Core entities:

- **User**: buyer, contributor, or admin account.
- **Photo**: uploaded asset metadata, raw object key, public preview URL, tags, county, price, license type, and processing status.
- **Transaction**: payment record with ACID constraints for contributor/platform revenue split.
- **License**: issued download/license record linked to a transaction, buyer, and photo.
- **RefreshToken**: hashed refresh token records for login sessions.

Important database choices:

- PostgreSQL is used because payment and payout data require consistency.
- Photo tag fields use PostgreSQL arrays and GIN indexes for efficient filtering.
- Original files are referenced by object keys, not stored directly in the database.

## API Documentation

When the app is running:

- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- OpenAPI schema: `/api/schema/`

Main API groups:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/photos`
- `GET /api/v1/photos/<photo_id>`
- `POST /api/v1/photos/upload-intent`
- `POST /api/v1/photos/<photo_id>/finalize`
- `GET /api/v1/contributor/dashboard`
- `GET /api/v1/licenses/download-token/<photo_id>`

## Image Upload Flow

1. A contributor authenticates and calls `POST /api/v1/photos/upload-intent`.
2. The API creates a pending `Photo` record and returns a presigned upload form for the private raw bucket.
3. The client uploads the original image directly to S3/DigitalOcean Spaces.
4. The client calls `POST /api/v1/photos/<photo_id>/finalize` with tags, county, license type, price, and description.
5. The API marks the photo as `processing` and queues a Celery task.
6. The worker downloads the private original, creates a compressed watermarked WebP preview, uploads it to the public preview bucket, and marks the photo as `active`.

## Local Development

Create and activate a virtual environment, then install dependencies:

```bash
pip install -r requirements.txt
```

Start Redis locally:

```bash
docker compose up -d redis
```

Run migrations:

```bash
python manage.py migrate
```

Run the Django API:

```bash
python manage.py runserver
```

Run the Celery worker in a second terminal:

```bash
celery -A config worker --loglevel=info
```

Generate static files:

```bash
python manage.py collectstatic --noinput
```

## Environment Variables

Required or commonly configured values:

```env
DATABASE_URL=postgres://...
JWT_SECRET_KEY=...
JWT_ACCESS_TOKEN_MINUTES=30
JWT_REFRESH_TOKEN_DAYS=30

CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_REGION_NAME=fra1
AWS_S3_ENDPOINT_URL=https://fra1.digitaloceanspaces.com
AWS_PRIVATE_RAW_BUCKET=lenske-private-raw
AWS_PUBLIC_PREVIEWS_BUCKET=lenske-public-previews
AWS_PUBLIC_PREVIEWS_BASE_URL=

AWS_UPLOAD_INTENT_EXPIRES_SECONDS=600
AWS_DOWNLOAD_URL_EXPIRES_SECONDS=600
LENSKE_WATERMARK_TEXT=LENS.KE
```

DigitalOcean App Platform currently provides storage-related variables in `app.yml`. Database, Redis, and secret values should be configured as encrypted environment variables in the DigitalOcean dashboard.

## DigitalOcean Deployment

The App Platform spec is in `app.yml`.

Deployed components:

- **Web service**: `lenske-api`
  - Runs migrations.
  - Starts Gunicorn with `config.wsgi:application`.
- **Worker**: `maji-pipeline-worker`
  - Runs `celery -A config worker --loglevel=info`.
  - Processes image watermarking and preview generation jobs.

The buildpack runs:

```bash
python manage.py collectstatic --noinput
```

`STATIC_ROOT` is configured as `BASE_DIR / "staticfiles"` so DigitalOcean can collect Django static files during deployment.

## Storage Strategy

- Raw high-resolution files go into a private bucket.
- Public previews are generated after upload and stored separately.
- Download access uses short-lived presigned URLs.
- The backend never exposes private raw object URLs directly.

## Current Limitations

- Payment webhook handling is not yet exposed as an API endpoint.
- License PDF generation is represented by the `License` model but not generated in this codebase yet.
- `DEBUG` and `ALLOWED_HOSTS` should be hardened before production traffic beyond staging/demo use.
- CDN/rate-limiting/API-gateway concerns are part of the broader design but are not implemented inside this Django app.

