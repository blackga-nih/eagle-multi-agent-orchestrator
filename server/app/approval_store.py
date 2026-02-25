
"""Approval Store -- DynamoDB-backed APPROVAL# multi-step review chain.

Phase 3 Step 16. Implements FAR-driven approval chains for acquisition packages.
Threshold logic:
    < $250,000   : [contracting_officer]
    < $750,000   : [contracting_officer, competition_advocate]
    >= $750,000  : [contracting_officer, competition_advocate, head_procuring_activity]

Entity format:
    PK:  APPROVAL#{tenant_id}
    SK:  APPROVAL#{package_id}#{step:02d}
"""
import os
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from boto3.dynamodb.conditions import Key

logger = logging.getLogger('eagle.approval_store')

# -- Configuration --------------------------------------------------------
TABLE_NAME = os.getenv('EAGLE_SESSIONS_TABLE', 'eagle')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

# -- FAR Threshold Constants -----------------------------------------------
_FAR_CHAIN_SMALL = [
    {'step': 1, 'role': 'contracting_officer'},
]
_FAR_CHAIN_MID = [
    {'step': 1, 'role': 'contracting_officer'},
    {'step': 2, 'role': 'competition_advocate'},
]
_FAR_CHAIN_LARGE = [
    {'step': 1, 'role': 'contracting_officer'},
    {'step': 2, 'role': 'competition_advocate'},
    {'step': 3, 'role': 'head_procuring_activity'},
]

THRESHOLD_MID = Decimal('250000')
THRESHOLD_LARGE = Decimal('750000')

# -- DynamoDB Client (lazy singleton) -------------------------------------
_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    return _dynamodb


def _get_table():
    return _get_dynamodb().Table(TABLE_NAME)


# -- Helpers ---------------------------------------------------------------

def _item_to_dict(item) -> dict:
    """Convert a raw DynamoDB item to a plain dict."""
    return dict(item)


def _sk(package_id: str, step: int) -> str:
    return f'APPROVAL#{package_id}#{step:02d}'


def _far_chain(estimated_value: Decimal) -> list[dict]:
    """Return the FAR-mandated role list for the given estimated contract value."""
    if estimated_value < THRESHOLD_MID:
        return _FAR_CHAIN_SMALL
    if estimated_value < THRESHOLD_LARGE:
        return _FAR_CHAIN_MID
    return _FAR_CHAIN_LARGE


# -- Core Functions --------------------------------------------------------

def create_approval_chain(
    tenant_id: str,
    package_id: str,
    estimated_value: Decimal,
) -> list[dict]:
    """Create the FAR-mandated approval chain for a package.

    Determines the required steps from estimated_value thresholds, writes each
    step to DynamoDB with status='pending', and returns the list of created items.
    """
    table = _get_table()
    now = datetime.utcnow().isoformat()
    chain_definition = _far_chain(estimated_value)

    created: list[dict] = []
    for step_def in chain_definition:
        step = step_def['step']
        item: dict = {
            'PK': f'APPROVAL#{tenant_id}',
            'SK': _sk(package_id, step),
            'package_id': package_id,
            'step': step,
            'role': step_def['role'],
            'status': 'pending',
            'comments': '',
            'required_for': [],
            'created_at': now,
        }
        try:
            table.put_item(Item=item)
            logger.debug(
                'approval_store.create_approval_chain: [%s/%s] step %s (%s) created',
                tenant_id, package_id, step, step_def['role'],
            )
            created.append(item)
        except (ClientError, BotoCoreError) as e:
            logger.error(
                'approval_store.create_approval_chain: failed step %s: %s', step, e
            )
            raise

    return created


def get_approval_step(
    tenant_id: str,
    package_id: str,
    step: int,
) -> Optional[dict]:
    """Fetch a single approval step item. Returns None if not found."""
    try:
        table = _get_table()
        response = table.get_item(
            Key={
                'PK': f'APPROVAL#{tenant_id}',
                'SK': _sk(package_id, step),
            }
        )
        raw = response.get('Item')
        return _item_to_dict(raw) if raw else None
    except (ClientError, BotoCoreError) as e:
        logger.error('approval_store.get_approval_step failed: %s', e)
        return None


def list_approval_chain(tenant_id: str, package_id: str) -> list[dict]:
    """Return all approval steps for a package, sorted by step number ascending."""
    table = _get_table()
    sk_prefix = f'APPROVAL#{package_id}#'

    try:
        response = table.query(
            KeyConditionExpression=(
                Key('PK').eq(f'APPROVAL#{tenant_id}')
                & Key('SK').begins_with(sk_prefix)
            ),
        )
        items = [_item_to_dict(i) for i in response.get('Items', [])]
        return sorted(items, key=lambda s: s.get('step', 0))
    except (ClientError, BotoCoreError) as e:
        logger.error('approval_store.list_approval_chain failed: %s', e)
        return []


def record_decision(
    tenant_id: str,
    package_id: str,
    step: int,
    status: str,
    comments: str = '',
    decided_by: str = '',
) -> Optional[dict]:
    """Record an approval decision (approved / rejected / returned) for one step.

    Sets decided_at to the current UTC time and updates status + comments.
    Returns the updated item dict, or None if the step was not found.
    """
    if status not in ('approved', 'rejected', 'returned'):
        raise ValueError(f'Invalid decision status: {status!r}')

    table = _get_table()
    now = datetime.utcnow().isoformat()

    try:
        response = table.update_item(
            Key={
                'PK': f'APPROVAL#{tenant_id}',
                'SK': _sk(package_id, step),
            },
            UpdateExpression=(
                'SET #st = :status, comments = :comments, '
                'decided_at = :decided_at, decided_by = :decided_by'
            ),
            ConditionExpression='attribute_exists(PK)',
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues={
                ':status': status,
                ':comments': comments,
                ':decided_at': now,
                ':decided_by': decided_by,
            },
            ReturnValues='ALL_NEW',
        )
        attrs = response.get('Attributes', {})
        return _item_to_dict(attrs) if attrs else None
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            logger.warning(
                'approval_store.record_decision: step not found [%s/%s step %s]',
                tenant_id, package_id, step,
            )
            return None
        logger.error('approval_store.record_decision failed: %s', e)
        return None
    except BotoCoreError as e:
        logger.error('approval_store.record_decision failed: %s', e)
        return None


def get_chain_status(tenant_id: str, package_id: str) -> dict:
    """Return a summary of the approval chain status for a package.

    Returns:
        {
            'overall': 'pending' | 'approved' | 'rejected',
            'steps': [...],
            'next_pending_step': int | None,
        }

    overall is:
      'rejected'  -- any step is rejected or returned
      'approved'  -- all steps are approved
      'pending'   -- otherwise
    """
    steps = list_approval_chain(tenant_id, package_id)

    if not steps:
        return {'overall': 'pending', 'steps': [], 'next_pending_step': None}

    statuses = {s['status'] for s in steps}
    if 'rejected' in statuses or 'returned' in statuses:
        overall = 'rejected'
    elif all(s['status'] == 'approved' for s in steps):
        overall = 'approved'
    else:
        overall = 'pending'

    next_pending = next(
        (s['step'] for s in steps if s['status'] == 'pending'), None
    )

    return {
        'overall': overall,
        'steps': steps,
        'next_pending_step': next_pending,
    }

