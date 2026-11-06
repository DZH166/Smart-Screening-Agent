"""Persist only allowlisted provider failure metadata. Never persist upstream messages."""
import json
import re

# https://docs.volcengine.com/docs/ark/error-codes
# Compare complete upstream codes. Arbitrary suffixes can contain user data.
CODE_GROUPS = {
    'parameters': {'InvalidParameter', 'InvalidParameter.UnsupportedParameter', 'MissingParameter'},
    'input_policy': {
        'InputTextSensitiveContentDetected', 'SensitiveContentDetected', 'InputTextRiskDetection',
        'InputImageSensitiveContentDetected', 'InputImageRiskDetection',
        'InputImageSensitiveContentDetected.PolicyViolation', 'InputTextSensitiveContentDetected.PolicyViolation',
        'InputImageSensitiveContentDetected.PrivacyInformation',
    },
    'output_policy': {
        'OutputImageSensitiveContentDetected', 'OutputTextSensitiveContentDetected',
        'OutputImageSensitiveContentDetected.PolicyViolation', 'OutputImageSensitiveContentDetected.DeepFake',
        'OutputImageRiskDetection', 'OutputTextRiskDetection',
    },
    'permission': {'Forbidden', 'Unauthorized', 'AuthenticationError', 'InvalidApiKey'},
    'configuration': {'InvalidEndpoint.ClosedEndpoint', 'ModelNotOpen', 'ModelNotFound'},
    'service': {'InternalServiceError', 'ContentSecurityDetectionError', 'ServiceUnavailable'},
    'rate_limit': {'RateLimitExceeded', 'RateLimitExceeded.EndpointRPMExceeded', 'RateLimitExceeded.EndpointTPMExceeded'},
}
CATEGORIES = {code: group for group, codes in CODE_GROUPS.items() for code in codes}
MESSAGES = {
    'input_policy': '服务拒绝了这次输入。请检查所选素材、参考图及要求后重新提交。',
    'output_policy': '素材可能包含受版权保护的角色，建议改用本地合成，或再重复试验两次；若仍报错，可能涉及侵权，请更换素材图。',
    'parameters': '服务未接受请求参数，请联系管理员检查图片尺寸和模型设置。',
    'configuration': '模型或接入点不可用，请联系管理员检查配置。',
    'permission': '服务未接受当前凭据或模型权限，请联系管理员。',
    'balance': '服务余额不足，请联系管理员检查账号。',
    'rate_limit': '服务当前限流，请稍后再提交。',
    'service': '提供商暂时不可用，请管理员检查服务状态。',
    'invalid_result': '返回内容未通过校验，请检查要求或素材后重新提交。',
    'unknown_result': '请求结果尚未确认，请先联系管理员核对记录。',
    'interrupted': '调用过程中断，请先核对请求记录。',
    'unclassified': '服务未完成请求，请联系管理员查看本次调用记录。',
    'not_recorded': '历史记录未保存具体错误码。',
    'in_progress': '正在等待服务返回。',
    'completed': '调用已完成。',
}
STAGES = {'prepare', 'provider', 'validation', 'transport', 'recovery', 'complete', 'unknown'}


def diagnostic(category='unclassified', stage='provider', http_status=None, upstream_code=None):
    return {
        'category': category if isinstance(category, str) and category in MESSAGES else 'unclassified',
        'stage': stage if isinstance(stage, str) and stage in STAGES else 'unknown',
        'http_status': http_status if type(http_status) is int and 100 <= http_status <= 599 else None,
        'upstream_code': upstream_code if isinstance(upstream_code, str) and upstream_code in CATEGORIES else None,
    }


def from_http(status, code=None):
    known = CATEGORIES.get(code) if isinstance(code, str) else None
    category = known or {401:'permission', 403:'permission', 402:'balance', 404:'configuration',
                         429:'rate_limit', 422:'parameters'}.get(status)
    if not category:
        category = 'service' if type(status) is int and 500 <= status <= 599 else 'unclassified'
    return diagnostic(category, 'provider', status, code)


def call_view(row):
    record = dict(row)
    raw = record.pop('error', None)
    category = {'SUCCEEDED':'completed','STARTED':'in_progress'}.get(row['status'], 'not_recorded')
    details = diagnostic(category, {'completed':'complete','in_progress':'prepare'}.get(category, 'unknown'))
    if isinstance(raw, str) and raw.startswith('{'):
        try:
            parsed = json.loads(raw)
        except (ValueError, RecursionError):
            parsed = None
        if isinstance(parsed, dict):
            details = diagnostic(**{k:parsed.get(k) for k in details})
    record['diagnostic'] = details
    record['error'] = None if row['status'] in ('SUCCEEDED','STARTED') else MESSAGES[details['category']]
    return record


def normalize_details(value, fallback=None):
    if not isinstance(value, dict):
        return fallback or diagnostic()
    return diagnostic(**{key: value.get(key) for key in ('category','stage','http_status','upstream_code')})


def safe_request_id(value):
    if not isinstance(value, str) or value.lower().startswith(('sk-', 'bearer', 'data:')):
        return None
    return value if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value) else None
