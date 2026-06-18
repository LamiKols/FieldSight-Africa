"""API routes for controlled metadata access."""

from flask import Blueprint, jsonify, request

from document_access import (
    authenticate_api_key,
    document_metadata_access_decision,
    externally_candidate_documents,
    log_document_access_attempt,
    record_api_usage,
    safe_document_metadata_payload,
)
from models import ActorDocument, AuditLog, db

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')


def request_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr)


def request_user_agent():
    return request.headers.get('User-Agent')


def raw_api_secret():
    auth_header = request.headers.get('Authorization', '').strip()
    if auth_header.lower().startswith('bearer '):
        return auth_header.split(None, 1)[1].strip()
    return request.headers.get('X-API-Key', '').strip()


@api_bp.route('/document-metadata')
def document_metadata():
    api_client, api_key = authenticate_api_key(raw_api_secret())
    filters = {
        'document_id': request.args.get('document_id'),
        'document_type': request.args.get('document_type'),
        'crop': request.args.get('crop'),
        'region': request.args.get('region'),
    }
    if not api_client or not api_key:
        db.session.add(AuditLog(
            user_id=None,
            organization_type='api',
            organization_id=None,
            action='api_document_metadata_unauthorized',
            entity_type='api_request',
            entity_id=None,
            after_values={'endpoint': request.path, 'method': request.method, 'status_code': 401},
            ip_address=request_ip(),
            user_agent=request_user_agent(),
        ))
        db.session.commit()
        return jsonify({'error': 'Invalid or unauthorized API key.'}), 401
    if not api_client.owner_user:
        record_api_usage(
            api_client,
            api_key,
            None,
            request.path,
            request.method,
            403,
            row_count=0,
            filters=filters,
            ip_address=request_ip(),
            user_agent=request_user_agent(),
        )
        db.session.commit()
        return jsonify({'error': 'API client is not linked to an entitlement owner.'}), 403

    documents = externally_candidate_documents()
    document_id = filters['document_id']
    if document_id:
        if not document_id.isdigit():
            record_api_usage(api_client, api_key, api_client.owner_user, request.path, request.method, 400, filters=filters, ip_address=request_ip(), user_agent=request_user_agent())
            db.session.commit()
            return jsonify({'error': 'document_id must be numeric.'}), 400
        document = ActorDocument.query.get(int(document_id))
        documents = [document] if document else []

    items = []
    blocked_reasons = []
    for document in documents:
        if not document:
            continue
        allowed, reasons, publish_control, _extraction_run = document_metadata_access_decision(
            api_client.owner_user,
            document,
            'api',
        )
        if allowed:
            payload = safe_document_metadata_payload(document, 'api', publish_control=publish_control)
            if filters['document_type'] and payload['document_type_code'] != filters['document_type']:
                continue
            if filters['crop'] and payload['crop'] != filters['crop']:
                continue
            if filters['region'] and payload['region_code'] != filters['region']:
                continue
            items.append(payload)
            log_document_access_attempt(
                document,
                'api_document_metadata_allowed',
                'api',
                user=api_client.owner_user,
                api_client=api_client,
                ip_address=request_ip(),
                user_agent=request_user_agent(),
            )
        else:
            blocked_reasons.append({'document_id': document.id, 'reasons': reasons})
            log_document_access_attempt(
                document,
                'api_document_metadata_blocked',
                'api',
                user=api_client.owner_user,
                api_client=api_client,
                ip_address=request_ip(),
                user_agent=request_user_agent(),
            )

    status_code = 200
    response_body = {
        'data': items,
        'count': len(items),
        'metadata_only': True,
    }
    if document_id and not items:
        status_code = 403 if blocked_reasons else 404
        response_body = {
            'error': 'Document metadata is not available for this API client.' if blocked_reasons else 'Document not found.',
            'metadata_only': True,
        }

    record_api_usage(
        api_client,
        api_key,
        api_client.owner_user,
        request.path,
        request.method,
        status_code,
        row_count=len(items),
        filters=filters,
        ip_address=request_ip(),
        user_agent=request_user_agent(),
    )
    db.session.commit()
    return jsonify(response_body), status_code
