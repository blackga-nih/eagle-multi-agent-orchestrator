"""Active AWS operations tool handlers."""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime

from botocore.exceptions import BotoCoreError, ClientError

from ..db_client import get_dynamodb, get_logs, get_s3
from ..document_key_utils import is_tenant_scoped_key
from ..session_scope import extract_user_id


def exec_s3_document_ops(
    params: dict, tenant_id: str, session_id: str | None = None
) -> dict:
    """Real S3 operations scoped per-user."""
    operation = params.get("operation", "list")
    bucket = params.get("bucket") or os.getenv(
        "S3_BUCKET", "eagle-documents-695681773636-dev"
    )
    key = params.get("key", "")
    content = params.get("content", "")
    user_id = extract_user_id(session_id)
    prefix = f"eagle/{tenant_id}/{user_id}/"

    s3 = get_s3()

    try:
        if operation == "list":
            resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=100)
            files = [
                {
                    "key": obj["Key"],
                    "size_bytes": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                }
                for obj in resp.get("Contents", [])
            ]
            return {
                "operation": "list",
                "bucket": bucket,
                "prefix": prefix,
                "file_count": len(files),
                "files": files,
            }

        if operation == "read":
            if not key:
                return {"error": "Missing 'key' parameter for read operation"}
            if key.startswith("eagle-knowledge-base/"):
                return {
                    "error": "Cannot read knowledge base documents via s3_document_ops. "
                    "Use knowledge_fetch(s3_key=...) or research(query=...) instead.",
                    "key": key,
                }
            if not is_tenant_scoped_key(key, tenant_id):
                key = prefix + key
            resp = s3.get_object(Bucket=bucket, Key=key)
            body = resp["Body"].read().decode("utf-8", errors="replace")
            return {
                "operation": "read",
                "key": key,
                "content_type": resp.get("ContentType", "unknown"),
                "size_bytes": resp.get("ContentLength", 0),
                "content": body[:50000],
            }

        if operation == "write":
            if not key:
                return {"error": "Missing 'key' parameter for write operation"}
            if not content:
                return {"error": "Missing 'content' parameter for write operation"}
            if not is_tenant_scoped_key(key, tenant_id):
                key = prefix + key
            s3.put_object(Bucket=bucket, Key=key, Body=content.encode("utf-8"))
            return {
                "operation": "write",
                "key": key,
                "bucket": bucket,
                "size_bytes": len(content.encode("utf-8")),
                "status": "success",
                "message": f"Document written to s3://{bucket}/{key}",
            }

        if operation == "delete":
            if not key:
                return {"error": "Missing 'key' parameter for delete operation"}
            if not is_tenant_scoped_key(key, tenant_id):
                key = prefix + key
            s3.delete_object(Bucket=bucket, Key=key)
            return {
                "operation": "delete",
                "key": key,
                "bucket": bucket,
                "status": "success",
                "message": f"Deleted s3://{bucket}/{key}",
            }

        if operation == "copy":
            destination_key = params.get("destination_key", "")
            if not key:
                return {"error": "Missing 'key' (source) parameter for copy operation"}
            if not destination_key:
                return {
                    "error": "Missing 'destination_key' parameter for copy operation"
                }
            if not is_tenant_scoped_key(key, tenant_id):
                key = prefix + key
            if not is_tenant_scoped_key(destination_key, tenant_id):
                destination_key = prefix + destination_key
            s3.copy_object(
                CopySource={"Bucket": bucket, "Key": key},
                Bucket=bucket,
                Key=destination_key,
            )
            return {
                "operation": "copy",
                "source_key": key,
                "destination_key": destination_key,
                "bucket": bucket,
                "status": "success",
                "message": f"Copied to s3://{bucket}/{destination_key}",
            }

        if operation in ("rename", "move"):
            destination_key = params.get("destination_key", "")
            if not key:
                return {
                    "error": "Missing 'key' (source) parameter for rename operation"
                }
            if not destination_key:
                return {
                    "error": "Missing 'destination_key' parameter for rename operation"
                }
            if not is_tenant_scoped_key(key, tenant_id):
                key = prefix + key
            if not is_tenant_scoped_key(destination_key, tenant_id):
                destination_key = prefix + destination_key
            s3.copy_object(
                CopySource={"Bucket": bucket, "Key": key},
                Bucket=bucket,
                Key=destination_key,
            )
            s3.delete_object(Bucket=bucket, Key=key)
            return {
                "operation": "rename",
                "source_key": key,
                "destination_key": destination_key,
                "bucket": bucket,
                "status": "success",
                "message": f"Renamed to s3://{bucket}/{destination_key}",
            }

        if operation == "exists":
            if not key:
                return {"error": "Missing 'key' parameter for exists operation"}
            if not is_tenant_scoped_key(key, tenant_id):
                key = prefix + key
            try:
                resp = s3.head_object(Bucket=bucket, Key=key)
                return {
                    "operation": "exists",
                    "key": key,
                    "exists": True,
                    "size_bytes": resp.get("ContentLength", 0),
                    "last_modified": resp.get("LastModified", "").isoformat()
                    if hasattr(resp.get("LastModified", ""), "isoformat")
                    else str(resp.get("LastModified", "")),
                    "content_type": resp.get("ContentType", "unknown"),
                }
            except ClientError as head_exc:
                if head_exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                    return {"operation": "exists", "key": key, "exists": False}
                raise

        if operation == "presign":
            if not key:
                return {"error": "Missing 'key' parameter for presign operation"}
            if not is_tenant_scoped_key(key, tenant_id):
                key = prefix + key
            expiry_seconds = int(params.get("expiry_seconds", 3600))
            url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expiry_seconds,
            )
            return {
                "operation": "presign",
                "key": key,
                "bucket": bucket,
                "url": url,
                "expires_in_seconds": expiry_seconds,
            }

        return {
            "error": f"Unknown operation: {operation}. Use list, read, write, delete, copy, rename, move, exists, or presign."
        }

    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        error_msg = exc.response["Error"]["Message"]
        if error_code in ("AccessDenied", "AccessDeniedException"):
            return {
                "error": f"AWS permission denied for S3 {operation}",
                "detail": error_msg,
                "suggestion": "The IAM user may not have the required S3 permissions. Contact your administrator.",
            }
        if error_code == "NoSuchKey":
            return {"error": f"File not found: {key}", "bucket": bucket}
        if error_code == "NoSuchBucket":
            return {"error": f"Bucket not found: {bucket}"}
        return {"error": f"S3 error ({error_code}): {error_msg}"}
    except BotoCoreError as exc:
        return {"error": f"AWS connection error: {str(exc)}"}


def exec_dynamodb_intake(params: dict, tenant_id: str) -> dict:
    """Real DynamoDB operations scoped per-tenant."""
    operation = params.get("operation", "list")
    table_name = params.get("table", "eagle")
    item_id = params.get("item_id", "")
    data = params.get("data", {})

    try:
        table = get_dynamodb().Table(table_name)

        if operation == "create":
            if not item_id:
                item_id = str(uuid.uuid4())[:8]
            item = {
                "PK": f"INTAKE#{tenant_id}",
                "SK": f"INTAKE#{item_id}",
                "item_id": item_id,
                "tenant_id": tenant_id,
                "created_at": datetime.utcnow().isoformat(),
                "status": "draft",
                **{k: v for k, v in data.items() if k not in ("PK", "SK")},
            }
            table.put_item(Item=item)
            return {
                "operation": "create",
                "item_id": item_id,
                "status": "created",
                "item": item,
            }

        if operation == "read":
            if not item_id:
                return {"error": "Missing 'item_id' for read operation"}
            resp = table.get_item(
                Key={"PK": f"INTAKE#{tenant_id}", "SK": f"INTAKE#{item_id}"}
            )
            item = resp.get("Item")
            if not item:
                return {"error": f"Intake record not found: {item_id}"}
            return {"operation": "read", "item": _serialize_ddb_item(item)}

        if operation == "update":
            if not item_id:
                return {"error": "Missing 'item_id' for update operation"}
            if not data:
                return {"error": "Missing 'data' for update operation"}
            update_parts = []
            expr_names = {}
            expr_values = {}
            for index, (key, value) in enumerate(data.items()):
                if key in ("PK", "SK"):
                    continue
                alias = f"#attr{index}"
                value_alias = f":val{index}"
                update_parts.append(f"{alias} = {value_alias}")
                expr_names[alias] = key
                expr_values[value_alias] = value
            if not update_parts:
                return {"error": "No valid fields to update"}
            update_parts.append("#upd = :updval")
            expr_names["#upd"] = "updated_at"
            expr_values[":updval"] = datetime.utcnow().isoformat()
            table.update_item(
                Key={"PK": f"INTAKE#{tenant_id}", "SK": f"INTAKE#{item_id}"},
                UpdateExpression="SET " + ", ".join(update_parts),
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values,
            )
            return {
                "operation": "update",
                "item_id": item_id,
                "status": "updated",
                "fields_updated": list(data.keys()),
            }

        if operation in ("list", "query"):
            from boto3.dynamodb.conditions import Key as DDBKey

            resp = table.query(
                KeyConditionExpression=DDBKey("PK").eq(f"INTAKE#{tenant_id}")
            )
            items = [_serialize_ddb_item(item) for item in resp.get("Items", [])]
            return {
                "operation": "list",
                "tenant_id": tenant_id,
                "count": len(items),
                "items": items,
            }

        if operation == "delete":
            if not item_id:
                return {"error": "Missing 'item_id' for delete operation"}
            table.delete_item(
                Key={"PK": f"INTAKE#{tenant_id}", "SK": f"INTAKE#{item_id}"}
            )
            return {"operation": "delete", "item_id": item_id, "status": "deleted"}

        if operation == "count":
            from boto3.dynamodb.conditions import Key as DDBKey

            resp = table.query(
                KeyConditionExpression=DDBKey("PK").eq(f"INTAKE#{tenant_id}"),
                Select="COUNT",
            )
            return {
                "operation": "count",
                "tenant_id": tenant_id,
                "count": resp.get("Count", 0),
            }

        if operation == "batch_get":
            item_ids_raw = params.get("item_ids", "")
            if not item_ids_raw:
                return {
                    "error": "Missing 'item_ids' for batch_get (comma-separated IDs)"
                }
            ids = [i.strip() for i in item_ids_raw.split(",") if i.strip()]
            if len(ids) > 100:
                return {"error": "batch_get supports max 100 items"}
            keys = [{"PK": f"INTAKE#{tenant_id}", "SK": f"INTAKE#{i}"} for i in ids]
            resp = get_dynamodb().batch_get_item(
                RequestItems={table_name: {"Keys": keys}}
            )
            items = [
                _serialize_ddb_item(item)
                for item in resp.get("Responses", {}).get(table_name, [])
            ]
            return {
                "operation": "batch_get",
                "requested": len(ids),
                "found": len(items),
                "items": items,
            }

        if operation == "batch_write":
            items_data = params.get("items", [])
            if not items_data:
                return {"error": "Missing 'items' for batch_write (list of dicts)"}
            if isinstance(items_data, str):
                import json as _json

                try:
                    items_data = _json.loads(items_data)
                except _json.JSONDecodeError:
                    return {"error": "Invalid JSON in 'items' parameter"}
            if len(items_data) > 25:
                return {"error": "batch_write supports max 25 items per call"}
            put_requests = []
            for item_data in items_data:
                bid = item_data.get("item_id", str(uuid.uuid4())[:8])
                item = {
                    "PK": f"INTAKE#{tenant_id}",
                    "SK": f"INTAKE#{bid}",
                    "item_id": bid,
                    "tenant_id": tenant_id,
                    "created_at": datetime.utcnow().isoformat(),
                    "status": "draft",
                    **{k: v for k, v in item_data.items() if k not in ("PK", "SK")},
                }
                put_requests.append({"PutRequest": {"Item": item}})
            get_dynamodb().batch_write_item(RequestItems={table_name: put_requests})
            return {
                "operation": "batch_write",
                "count": len(put_requests),
                "status": "created",
            }

        return {
            "error": f"Unknown operation: {operation}. Use create, read, update, delete, list, query, count, batch_get, or batch_write."
        }

    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        error_msg = exc.response["Error"]["Message"]
        if error_code in ("AccessDenied", "AccessDeniedException"):
            return {
                "error": f"AWS permission denied for DynamoDB {operation}",
                "detail": error_msg,
                "suggestion": "The IAM user may not have the required DynamoDB permissions. Contact your administrator.",
            }
        if error_code == "ResourceNotFoundException":
            return {
                "error": f"DynamoDB table '{table_name}' not found. It may need to be created."
            }
        return {"error": f"DynamoDB error ({error_code}): {error_msg}"}
    except BotoCoreError as exc:
        return {"error": f"AWS connection error: {str(exc)}"}


def exec_cloudwatch_logs(params: dict, tenant_id: str) -> dict:
    """Real CloudWatch Logs operations with optional user_id scoping."""
    operation = params.get("operation", "recent")
    log_group = params.get("log_group", "/eagle/app")
    filter_pattern = params.get("filter_pattern", "")
    limit = params.get("limit", 50)
    start_time_str = params.get("start_time", "")
    end_time_str = params.get("end_time", "")
    user_id = params.get("user_id", "")

    try:
        logs = get_logs()
        now = int(time.time() * 1000)
        start_time = now - (3600 * 1000)
        end_time = now

        if start_time_str:
            if start_time_str.startswith("-"):
                value = start_time_str[1:-1]
                unit = start_time_str[-1]
                multipliers = {"m": 60, "h": 3600, "d": 86400}
                start_time = now - (int(value) * multipliers.get(unit, 3600) * 1000)
            else:
                try:
                    dt = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                    start_time = int(dt.timestamp() * 1000)
                except ValueError:
                    pass

        if end_time_str:
            try:
                dt = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
                end_time = int(dt.timestamp() * 1000)
            except ValueError:
                pass

        if operation == "search":
            scoped_pattern = filter_pattern
            if tenant_id and tenant_id not in (filter_pattern or ""):
                scoped_pattern = f'"{tenant_id}" {scoped_pattern}'.strip()
            if user_id and user_id not in scoped_pattern:
                scoped_pattern = f'"{user_id}" {scoped_pattern}'.strip()
            resp = logs.filter_log_events(
                logGroupName=log_group,
                filterPattern=scoped_pattern,
                startTime=start_time,
                endTime=end_time,
                limit=min(limit, 100),
            )
            events = [
                {
                    "timestamp": event["timestamp"],
                    "message": event["message"][:500],
                    "logStreamName": event.get("logStreamName", ""),
                }
                for event in resp.get("events", [])
            ]
            return {
                "operation": "search",
                "log_group": log_group,
                "filter_pattern": scoped_pattern,
                "event_count": len(events),
                "events": events,
            }

        if operation == "recent":
            kwargs = {
                "logGroupName": log_group,
                "startTime": start_time,
                "endTime": end_time,
                "limit": min(limit, 100),
            }
            if user_id:
                kwargs["filterPattern"] = f'"{user_id}"'
            resp = logs.filter_log_events(**kwargs)
            events = [
                {
                    "timestamp": event["timestamp"],
                    "message": event["message"][:500],
                    "logStreamName": event.get("logStreamName", ""),
                }
                for event in resp.get("events", [])
            ]
            result = {
                "operation": "recent",
                "log_group": log_group,
                "event_count": len(events),
                "events": events,
            }
            if user_id:
                result["user_id_filter"] = user_id
            return result

        if operation == "get_stream":
            resp = logs.describe_log_streams(
                logGroupName=log_group,
                orderBy="LastEventTime",
                descending=True,
                limit=5,
            )
            streams = [
                {
                    "logStreamName": stream["logStreamName"],
                    "lastEventTimestamp": stream.get("lastEventTimestamp", 0),
                }
                for stream in resp.get("logStreams", [])
            ]
            return {
                "operation": "get_stream",
                "log_group": log_group,
                "streams": streams,
            }

        if operation == "insights":
            query = params.get("query", "")
            if not query:
                return {
                    "error": "Missing 'query' parameter for insights operation (CloudWatch Logs Insights query string)"
                }
            query_id = logs.start_query(
                logGroupName=log_group,
                startTime=start_time // 1000,
                endTime=end_time // 1000,
                queryString=query,
                limit=min(limit, 1000),
            )["queryId"]
            # Poll for results (max 10 attempts, 1s apart)
            import time as _time_mod

            results = []
            status = "Running"
            for _ in range(10):
                _time_mod.sleep(1)
                resp = logs.get_query_results(queryId=query_id)
                status = resp.get("status", "Unknown")
                if status in ("Complete", "Failed", "Cancelled"):
                    results = resp.get("results", [])
                    break
            formatted = []
            for row in results[:100]:
                formatted.append({field["field"]: field["value"] for field in row})
            return {
                "operation": "insights",
                "log_group": log_group,
                "query": query,
                "status": status,
                "result_count": len(formatted),
                "results": formatted,
            }

        if operation == "list_groups":
            prefix_filter = params.get("prefix", "")
            kwargs = {"limit": min(limit, 50)}
            if prefix_filter:
                kwargs["logGroupNamePrefix"] = prefix_filter
            resp = logs.describe_log_groups(**kwargs)
            groups = [
                {
                    "logGroupName": g["logGroupName"],
                    "storedBytes": g.get("storedBytes", 0),
                    "retentionInDays": g.get("retentionInDays"),
                    "creationTime": g.get("creationTime", 0),
                }
                for g in resp.get("logGroups", [])
            ]
            return {
                "operation": "list_groups",
                "count": len(groups),
                "log_groups": groups,
            }

        return {
            "error": f"Unknown operation: {operation}. Use search, recent, get_stream, insights, or list_groups."
        }

    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        error_msg = exc.response["Error"]["Message"]
        if error_code in ("AccessDenied", "AccessDeniedException"):
            return {
                "error": f"AWS permission denied for CloudWatch Logs {operation}",
                "detail": error_msg,
                "suggestion": "The IAM user may not have the required CloudWatch Logs permissions. Contact your administrator.",
            }
        if error_code == "ResourceNotFoundException":
            return {"error": f"Log group '{log_group}' not found."}
        return {"error": f"CloudWatch error ({error_code}): {error_msg}"}
    except BotoCoreError as exc:
        return {"error": f"AWS connection error: {str(exc)}"}


def _serialize_ddb_item(item: dict) -> dict:
    from decimal import Decimal

    result = {}
    for key, value in item.items():
        if isinstance(value, Decimal):
            result[key] = float(value) if value % 1 else int(value)
        else:
            result[key] = value
    return result
