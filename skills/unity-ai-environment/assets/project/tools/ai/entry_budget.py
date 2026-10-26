"""Prove a complete AGENTS entry fits the portable 500-token budget offline."""
import hashlib
import re


def check_entry(text, certificate, *, require_core=False):
    limit = 500
    counts = {name: len(text.encode('utf-8')) for name in ('cl100k_base', 'o200k_base')}
    method = 'utf8-bound'
    valid = (
        isinstance(certificate, dict)
        and type(certificate.get('schema_version')) is int
        and certificate['schema_version'] == 1
        and type(certificate.get('limit')) is int
        and certificate['limit'] == limit
        and isinstance(certificate.get('template_sha256'), str)
        and re.fullmatch('[0-9a-f]{64}', certificate['template_sha256']) is not None
        and isinstance(certificate.get('token_counts'), dict)
        and all(type(certificate['token_counts'].get(name)) is int
                and 0 <= certificate['token_counts'][name] <= limit for name in counts)
    )
    start = '<!-- ai-environment:start -->'
    end = '<!-- ai-environment:end -->\n'
    core_matches = False
    if valid and text.count(start) == 1 and text.count('<!-- ai-environment:end -->') == 1:
        first, last = text.index(start), text.find(end)
        if last >= first:
            last += len(end)
            block = text[first:last]
            if hashlib.sha256(block.encode('utf-8')).hexdigest() == certificate['template_sha256']:
                core_matches = True
                extra = len((text[:first] + text[last:]).encode('utf-8'))
                # Retokenizing across a manual/template boundary may change tokens.
                allowance = extra + 64 if extra else 0
                counts = {name: certificate['token_counts'][name] + allowance for name in counts}
                method = 'certificate-plus-utf8-bound' if extra else 'certificate'
    errors = []
    if require_core and not core_matches:
        errors.append('Root AGENTS managed core differs from its certificate; restore the full '
                      'reviewed template and certificate, or review and recertify the full core.')
    if any(count > limit for count in counts.values()):
        errors.append(f'Complete AGENTS entry cannot be proven within {limit} tokens '
                      f'using {method}: ' + ', '.join(f'{name}={count}' for name, count in counts.items()))
    return {'ok': not errors, 'limit': limit, 'method': method,
            'token_counts': counts, 'core_matches': core_matches, 'errors': errors}
