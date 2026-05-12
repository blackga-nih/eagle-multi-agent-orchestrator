"""End-to-end smoke for upload → attach → list → download flow.

Validates that:

1. The user can create a package via REST.
2. The chat upload-button code path (`POST /api/packages/{id}/attachments`)
   accepts a real file and persists it to S3 + DynamoDB.
3. Listing attachments (`GET /api/packages/{id}/attachments`) surfaces the
   uploaded item — this is what the frontend "Package Attachments" panel
   reads to render the user-uploaded-docs section.
4. Downloading the package zip (`GET /api/packages/{id}/export/zip`)
   actually contains the uploaded file inside the
   `09_Attachments/{category}/` folder.

Runs locally with moto-mocked S3 + DynamoDB so it doesn't need VPC access
or AWS SSO. The same code paths are exercised by the deployed backend.
"""

from __future__ import annotations

import io
import os
import re
import sys
import zipfile

import boto3
import pytest
from moto import mock_aws

# ── Test environment setup ───────────────────────────────────────────────────
# Set BEFORE any app.* import so module-level os.getenv() reads dev defaults.
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
# .env sets AWS_PROFILE=eagle; clear it so boto3 doesn't try the real SSO
# profile while moto is active.
os.environ.pop("AWS_PROFILE", None)
os.environ["EAGLE_SESSIONS_TABLE"] = "eagle-test"
os.environ["S3_BUCKET"] = "eagle-test-bucket"
os.environ["DOCUMENT_BUCKET"] = "eagle-test-bucket"
os.environ["EAGLE_S3_BUCKET"] = "eagle-test-bucket"
os.environ["DEV_MODE"] = "true"
os.environ["EAGLE_BEDROCK_DISABLED"] = "1"
os.environ["EAGLE_DISABLE_LANGFUSE"] = "1"
# Disable conftest's CloudWatch result-persistence — it tries to PutItem on
# the real `eagle` table during teardown and clutters output with
# UnrecognizedClientException warnings.
os.environ["EAGLE_PERSIST_TEST_RESULTS"] = "false"

TENANT_ID = "smoke-tenant"
USER_ID = "smoke-user"
TABLE_NAME = os.environ["EAGLE_SESSIONS_TABLE"]
BUCKET_NAME = os.environ["S3_BUCKET"]


@pytest.fixture(scope="module")
def aws_mock():
    """Spin up moto for the entire smoke module."""
    with mock_aws():
        # DDB single-table — same schema as core-stack.ts
        ddb = boto3.client("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=TABLE_NAME,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
                {"AttributeName": "GSI2PK", "AttributeType": "S"},
                {"AttributeName": "GSI2SK", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "GSI2",
                    "KeySchema": [
                        {"AttributeName": "GSI2PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI2SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
        )

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET_NAME)

        # Reset cached AWS-client singletons in app.db_client so the module
        # picks up the moto endpoint instead of any prior real-AWS client.
        if "app.db_client" in sys.modules:
            mod = sys.modules["app.db_client"]
            for fn in ("get_dynamodb", "get_s3", "get_logs", "get_table"):
                if hasattr(mod, fn):
                    getattr(mod, fn).cache_clear()

        yield


@pytest.fixture(scope="module")
def app_module(aws_mock):
    """Import app.main inside the moto context so its boto3 clients
    point at the mock endpoint."""
    # app.main calls dotenv.load_dotenv(override=True) at import time,
    # which clobbers our test-mode env vars (EAGLE_SESSIONS_TABLE,
    # S3_BUCKET, AWS_PROFILE) by re-reading server/.env. Patch it to a
    # no-op so our os.environ values stick.
    import dotenv
    _orig_load_dotenv = dotenv.load_dotenv
    dotenv.load_dotenv = lambda *args, **kwargs: True

    # Drop any cached app.* modules so a clean import binds against moto
    # and re-reads the test-mode env we set at module-load time.
    for name in list(sys.modules.keys()):
        if name.startswith("app.") or name == "app":
            sys.modules.pop(name, None)

    try:
        import app.main as main_module  # noqa: WPS433
    finally:
        dotenv.load_dotenv = _orig_load_dotenv

    # Sanity diagnostic: confirm app.db_client bound the moto-created table.
    import app.db_client as dbc
    print(
        f"[smoke] EAGLE_TABLE_NAME={dbc.EAGLE_TABLE_NAME} "
        f"resolved_table={dbc.get_table().table_name}"
    )
    return main_module


@pytest.fixture(scope="module")
def client(app_module):
    """FastAPI TestClient hitting the live router stack."""
    from fastapi.testclient import TestClient
    from app.cognito_auth import UserContext
    from app.routers.dependencies import get_user_from_header

    def _override_user() -> UserContext:
        return UserContext(
            user_id=USER_ID,
            tenant_id=TENANT_ID,
            email=f"{USER_ID}@example.com",
            tier="basic",
            roles=["user"],
        )

    app_module.app.dependency_overrides[get_user_from_header] = _override_user
    with TestClient(app_module.app) as c:
        yield c


# ── Scenario ─────────────────────────────────────────────────────────────────


def test_upload_attach_export_full_flow(client):
    # 1. Create a package
    resp = client.post(
        "/api/packages",
        json={
            "title": "Smoke — Microscope acquisition",
            "requirement_type": "products",
            "estimated_value": "150000",
        },
    )
    assert resp.status_code == 200, f"create package failed: {resp.status_code} {resp.text}"
    pkg = resp.json()
    package_id = pkg["package_id"]
    assert package_id, "package_id missing on create response"

    # 2. Upload a file via the chat-upload-button endpoint (package-scoped)
    file_bytes = b"This is a smoke-test requirements document.\nLine 2 of the doc.\n"
    file_name = "smoke_requirements.txt"
    upload = client.post(
        f"/api/packages/{package_id}/attachments",
        files={"file": (file_name, file_bytes, "text/plain")},
        data={"title": "Smoke Requirements", "category": "requirements_evidence"},
    )
    assert upload.status_code == 200, (
        f"upload failed: {upload.status_code} {upload.text}"
    )
    attachment = upload.json()
    attachment_id = attachment.get("attachment_id")
    assert attachment_id, f"attachment_id missing: {attachment}"
    assert attachment.get("filename"), "filename missing on attachment"
    assert attachment.get("size_bytes") == len(file_bytes), "size_bytes mismatch"
    assert attachment.get("category") == "requirements_evidence"
    assert attachment.get("include_in_zip") is True, "default include_in_zip should be True"
    assert attachment.get("s3_key"), "s3_key missing on attachment"

    # 3. List attachments — this is what the frontend Package Attachments
    #    panel reads to render the user-uploaded-docs section.
    listing = client.get(f"/api/packages/{package_id}/attachments")
    assert listing.status_code == 200, listing.text
    listed = listing.json()
    assert isinstance(listed, dict) and "attachments" in listed, listed
    assert listed["count"] >= 1, f"no attachments listed: {listed}"
    ids = [a["attachment_id"] for a in listed["attachments"]]
    assert attachment_id in ids, f"uploaded attachment not in list: {ids}"

    # 4. Download package zip — confirm uploaded file is in the
    #    `09_Attachments/{category}/` folder of the zip the user downloads.
    export = client.get(
        f"/api/packages/{package_id}/export/zip",
        params={"format": "md"},
    )
    assert export.status_code == 200, f"export failed: {export.status_code} {export.text[:300]}"
    assert export.headers.get("content-type", "").startswith("application/zip"), (
        f"export content-type unexpected: {export.headers.get('content-type')}"
    )

    zip_buf = io.BytesIO(export.content)
    with zipfile.ZipFile(zip_buf, "r") as zf:
        names = zf.namelist()

    assert names, "downloaded zip is empty"

    user_uploaded_entries = [
        n for n in names
        if n.startswith("09_Attachments/requirements_evidence/")
    ]
    assert user_uploaded_entries, (
        "no entries under 09_Attachments/requirements_evidence/ in zip — "
        f"got: {names}"
    )

    # The attachment file name in the zip is built from
    # _build_attachment_export_name(...) which uses the last 8 chars of
    # the attachment_id as the disambiguator. Check by that suffix so the
    # test stays stable across naming tweaks.
    id_suffix = re.sub(r"[^\w\-]", "_", attachment_id)[-8:]
    matching = [n for n in user_uploaded_entries if id_suffix in n]
    assert matching, (
        f"attachment_id {attachment_id[:8]} not found in zip entry names: "
        f"{user_uploaded_entries}"
    )

    # And the bytes round-trip
    with zipfile.ZipFile(io.BytesIO(export.content)) as zf:
        body = zf.read(matching[0])
    assert body == file_bytes, "zip-extracted bytes != uploaded bytes"


def test_listing_response_shape_for_attachments_panel(client):
    """The Package Attachments panel reads several fields per attachment.

    Locks the wire shape so refactors in the store/router don't silently
    drop fields the frontend `attachment-row` template relies on.
    """
    pkg = client.post(
        "/api/packages",
        json={
            "title": "Smoke — Listing shape",
            "requirement_type": "services",
            "estimated_value": "120000",
        },
    ).json()
    package_id = pkg["package_id"]

    file_bytes = b"prior SOW reference\n"
    upload = client.post(
        f"/api/packages/{package_id}/attachments",
        files={"file": ("prior_sow.txt", file_bytes, "text/plain")},
        data={
            "title": "Prior SOW Reference",
            "category": "prior_artifact",
        },
    )
    assert upload.status_code == 200, upload.text
    attachment_id = upload.json()["attachment_id"]

    listing = client.get(f"/api/packages/{package_id}/attachments").json()
    assert listing["count"] == 1, listing
    row = listing["attachments"][0]
    assert row["attachment_id"] == attachment_id

    # Fields the panel renders. If any of these go missing the
    # user-uploaded section degrades silently — guard them here.
    expected_fields = {
        "attachment_id",
        "package_id",
        "attachment_type",
        "category",
        "usage",
        "include_in_zip",
        "title",
        "display_name",
        "filename",
        "original_filename",
        "file_type",
        "content_type",
        "size_bytes",
        "s3_key",
        "created_at",
    }
    missing = expected_fields - set(row.keys())
    assert not missing, f"listing row missing required fields for panel: {missing}"

    assert row["category"] == "prior_artifact"
    # Default usage is 'reference' when no linked_doc_type is provided.
    assert row["usage"] == "reference"
    assert row["title"] == "Prior SOW Reference"
    assert row["display_name"] == "Prior SOW Reference"


def test_include_in_zip_false_excludes_from_download(client):
    """`include_in_zip=false` must hold the attachment out of the export."""
    pkg = client.post(
        "/api/packages",
        json={
            "title": "Smoke — include_in_zip toggle",
            "requirement_type": "services",
            "estimated_value": "100000",
        },
    ).json()
    package_id = pkg["package_id"]

    keep_bytes = b"keep this in the zip\n"
    drop_bytes = b"hold this out of the zip\n"
    keep_resp = client.post(
        f"/api/packages/{package_id}/attachments",
        files={"file": ("keep.txt", keep_bytes, "text/plain")},
        data={"category": "requirements_evidence", "include_in_zip": "true"},
    )
    drop_resp = client.post(
        f"/api/packages/{package_id}/attachments",
        files={"file": ("drop.txt", drop_bytes, "text/plain")},
        data={"category": "requirements_evidence", "include_in_zip": "false"},
    )
    assert keep_resp.status_code == 200, keep_resp.text
    assert drop_resp.status_code == 200, drop_resp.text
    keep_id = keep_resp.json()["attachment_id"]
    drop_id = drop_resp.json()["attachment_id"]
    assert drop_resp.json()["include_in_zip"] is False

    export = client.get(
        f"/api/packages/{package_id}/export/zip",
        params={"format": "md"},
    )
    assert export.status_code == 200, export.text[:300]

    with zipfile.ZipFile(io.BytesIO(export.content)) as zf:
        names = zf.namelist()

    keep_suffix = re.sub(r"[^\w\-]", "_", keep_id)[-8:]
    drop_suffix = re.sub(r"[^\w\-]", "_", drop_id)[-8:]
    assert any(keep_suffix in n for n in names), (
        f"include_in_zip=true attachment ({keep_suffix}) missing from zip: {names}"
    )
    assert not any(drop_suffix in n for n in names), (
        f"include_in_zip=false attachment ({drop_suffix}) leaked into zip: {names}"
    )


def test_image_upload_round_trips_through_zip(client):
    """Screenshots / PNG uploads go through a different attachment_type
    branch (`image`, no markdown sibling). Guard that the zip still gets
    the file under `09_Attachments/{category}/`."""
    pkg = client.post(
        "/api/packages",
        json={
            "title": "Smoke — image attach",
            "requirement_type": "services",
            "estimated_value": "85000",
        },
    ).json()
    package_id = pkg["package_id"]

    # Minimal valid PNG: 1×1 transparent pixel.
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452"
        "00000001000000010806000000"
        "1f15c4890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
    upload = client.post(
        f"/api/packages/{package_id}/attachments",
        files={"file": ("screenshot.png", png_bytes, "image/png")},
        data={"category": "technical_evidence", "title": "Lab screenshot"},
    )
    assert upload.status_code == 200, upload.text
    row = upload.json()
    # `screenshot.png` filename triggers the `screenshot` sub-branch of
    # _detect_attachment_type — both `image` and `screenshot` are valid
    # responses for this code path.
    assert row["attachment_type"] in {"image", "screenshot"}, row["attachment_type"]
    assert row["category"] == "technical_evidence"

    export = client.get(
        f"/api/packages/{package_id}/export/zip",
        params={"format": "md"},
    )
    assert export.status_code == 200, export.text[:300]

    with zipfile.ZipFile(io.BytesIO(export.content)) as zf:
        names = zf.namelist()
        suffix = re.sub(r"[^\w\-]", "_", row["attachment_id"])[-8:]
        target = next(
            (
                n for n in names
                if n.startswith("09_Attachments/technical_evidence/")
                and suffix in n
            ),
            None,
        )
        assert target, f"image attachment not in zip: {names}"
        assert zf.read(target) == png_bytes, "image bytes corrupted on zip round-trip"


# Minimal valid PNG: 1×1 transparent pixel. Used by the workspace-upload
# tests below to exercise /api/documents/upload (no package_id branch).
_MIN_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452"
    "00000001000000010806000000"
    "1f15c4890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def test_workspace_png_upload_no_package(client):
    """Reproduces the user's report: clicking the attach button with NO
    active package routes the upload to `/api/documents/upload`. The
    handler walks PDF parsing, classification, markdown conversion, and
    template standardization paths — every one of them needs to be safe
    for image bytes (PNG) which can't be parsed as text or DOCX.

    Without an active package the chat-upload-button calls
    `uploadDocument` (not `uploadPackageAttachment`), so this is the
    real-world path the user hit when uploading a screenshot.
    """
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("photo.png", _MIN_PNG_BYTES, "image/png")},
    )
    assert upload.status_code == 200, (
        f"workspace png upload failed: {upload.status_code} {upload.text[:300]}"
    )
    row = upload.json()
    assert row.get("document_id"), f"no document_id on upload: {row}"
    assert row.get("content_type") == "image/png"
    assert row.get("size_bytes") == len(_MIN_PNG_BYTES)
    # The PNG path should not be misclassified — extract_text_preview is
    # None for images and convert_to_markdown returns None for images, so
    # the classification falls back to filename → unknown.
    cls = row.get("classification") or {}
    # The doc_type may be "unknown" or guessed — either is fine; what
    # matters is that the request didn't 500 out.
    assert "doc_type" in cls, f"classification dict malformed: {cls}"


def test_workspace_jpeg_upload_no_package(client):
    """Sister test for JPEG — same code path as PNG, different MIME."""
    # 1×1 JPEG (smallest valid JPEG)
    jpeg_bytes = bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d0d1832211c2132323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232ffc00011080001000103012200021101031101ffc4001f0000010501010101010100000000000000000102030405060708090a0bffc400b5100002010303020403050504040000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a535455565758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffc4001f0100030101010101010101010000000000000102030405060708090a0bffc400b51100020102040403040705040400010277000102031104052131061241510761711322328108144291a1b1c109233352f0156272d10a162434e125f11718191a262728292a35363738393a434445464748494a535455565758595a636465666768696a737475767778797a82838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9faffda000c03010002110311003f00fbfeffd9"
    )
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("camera.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert upload.status_code == 200, (
        f"workspace jpeg upload failed: {upload.status_code} {upload.text[:300]}"
    )
    assert upload.json().get("content_type") == "image/jpeg"


def test_workspace_png_upload_with_octet_stream_content_type(client):
    """Browsers occasionally send `application/octet-stream` for files
    when the OS hasn't tagged a MIME type. The current upload handler
    rejects this with a 415 even for a real PNG — guard the user-visible
    error message stays specific so the frontend can surface it cleanly.
    """
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("photo.png", _MIN_PNG_BYTES, "application/octet-stream")},
    )
    # Either the handler accepts (sniffs by extension) or returns a
    # specific 415. A 500 here is a regression — that's what the user
    # hit when nothing rendered after attach.
    assert upload.status_code in (200, 415), (
        f"unexpected status for octet-stream png: {upload.status_code} {upload.text[:300]}"
    )
    if upload.status_code == 415:
        # The error must mention the unsupported MIME so the frontend
        # surface stays understandable.
        assert "Unsupported file type" in upload.text, upload.text
