"""Contact imports from several sources (Google Contacts, Outlook, Antares CSV, generic CSV, vCard).

Every source is reduced to the same neutral record, then normalised (names, BR phone numbers, e-mails)
and de-duplicated before anything is written, so a preview and the real import share one code path.
"""

import csv
import io
import re
import unicodedata

from ..models import Contact

MAX_ROWS = 10000
FIELD_LABELS = {
    'first_name': 'Nome',
    'middle_name': 'Nome do meio',
    'last_name': 'Sobrenome',
    'full_name': 'Nome completo',
    'email': 'E-mail',
    'phone': 'Telefone',
    'company': 'Empresa',
    'position': 'Cargo',
    'notes': 'Observações',
    'source': 'Origem',
    'tags': 'Tags / etiquetas',
}
MULTI = {'email', 'phone', 'tags'}


def norm(text):
    return re.sub(
        r'[^a-z0-9]+', ' ', unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode().lower()
    ).strip()


# Header synonyms for generic spreadsheets (compared after `norm`).
SYNONYMS = {
    'full_name': [
        'name',
        'nome',
        'nome completo',
        'full name',
        'display name',
        'contato',
        'cliente',
        'razao social',
        'file as',
    ],
    'first_name': ['first name', 'primeiro nome', 'given name', 'nome proprio'],
    'middle_name': ['middle name', 'nome do meio', 'additional name'],
    'last_name': ['last name', 'sobrenome', 'ultimo nome', 'family name', 'surname'],
    'email': [
        'email',
        'e mail',
        'email address',
        'e mail address',
        'e mail 1 value',
        'e mail 2 value',
        'e mail 3 value',
        'email 1',
        'email 2',
        'correio eletronico',
    ],
    'phone': [
        'phone',
        'telefone',
        'celular',
        'whatsapp',
        'fone',
        'mobile',
        'mobile phone',
        'tel',
        'telefone celular',
        'telefone comercial',
        'phone 1 value',
        'phone 2 value',
        'phone 3 value',
        'phone 4 value',
        'home phone',
        'business phone',
        'primary phone',
        'other phone',
    ],
    'company': ['company', 'empresa', 'organization', 'organization name', 'organizacao', 'organisation'],
    'position': ['position', 'cargo', 'job title', 'title', 'organization title', 'funcao', 'ocupacao'],
    'notes': ['notes', 'notas', 'observacoes', 'observacao', 'obs', 'comments', 'comentarios', 'anotacoes'],
    'source': ['source', 'origem', 'fonte', 'canal'],
    'tags': ['tags', 'tag', 'labels', 'label', 'etiquetas', 'categorias', 'categories', 'grupos', 'group membership'],
}


def decode(data: bytes) -> str:
    if data[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return data.decode('utf-16')
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return data.decode('cp1252', errors='replace')


def detect_format(text, headers=None):
    if text.lstrip().upper().startswith('BEGIN:VCARD'):
        return 'vcard'
    if not headers:
        return 'generic'
    lowered = {norm(h) for h in headers}
    if 'e mail 1 value' in lowered or ('first name' in lowered and 'phone 1 value' in lowered):
        return 'google'
    if 'e mail address' in lowered or 'mobile phone' in lowered or 'business phone' in lowered:
        return 'outlook'
    if 'name' in lowered and lowered <= {
        'name',
        'email',
        'phone',
        'position',
        'source',
        'notes',
        'tags',
        'custom fields',
        'custom_fields'.replace('_', ' '),
    }:
        return 'antares'
    return 'generic'


FORMAT_LABELS = {
    'google': 'Google Contatos',
    'outlook': 'Outlook',
    'antares': 'Modelo do Antares',
    'generic': 'Planilha CSV',
    'vcard': 'vCard (.vcf)',
}


def read_csv(text):
    text = text.lstrip('﻿')
    sample = text[:8192]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=',;\t|').delimiter
    except csv.Error:
        delimiter = ';' if sample.count(';') > sample.count(',') else ','
    reader = csv.reader(io.StringIO(text, newline=''), delimiter=delimiter)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return [], []
    headers = [h.strip() for h in rows[0]]
    return headers, rows[1:]


def suggest_mapping(headers):
    """Maps each target field to the matching header names, in file order."""
    mapping = {key: [] for key in FIELD_LABELS}
    by_norm = {}
    for header in headers:
        by_norm.setdefault(norm(header), header)
    for key, names in SYNONYMS.items():
        for header in headers:
            if norm(header) in names and (key in MULTI or not mapping[key]):
                mapping[key].append(header)
    # Prefer first/last name over a lone "full name" only when both parts exist.
    if mapping['first_name'] or mapping['last_name']:
        mapping['full_name'] = [h for h in mapping['full_name'] if norm(h) != 'file as']
    # Google keeps one label column per field ("Phone 1 - Label"): never map those as values.
    for key in ('phone', 'email'):
        mapping[key] = [h for h in mapping[key] if 'label' not in norm(h).split()]
    return {key: value for key, value in mapping.items() if value}


# ---- vCard ----
def read_vcard(text):
    lines = re.sub(r'\r?\n[ \t]', '', text).splitlines()
    cards, card = [], None
    for line in lines:
        upper = line.upper()
        if upper.startswith('BEGIN:VCARD'):
            card = {'phone': [], 'email': [], 'tags': []}
        elif upper.startswith('END:VCARD'):
            if card is not None:
                cards.append(card)
            card = None
        elif card is not None and ':' in line:
            key, value = line.split(':', 1)
            name = key.split(';')[0].upper().split('.')[-1]
            value = value.replace('\\n', '\n').replace('\\,', ',').replace('\\;', ';').strip()
            if name == 'FN':
                card['full_name'] = value
            elif name == 'N' and 'full_name' not in card:
                parts = (value.split(';') + ['', '', '', '', ''])[:5]
                card['last_name'], card['first_name'], card['middle_name'] = parts[0], parts[1], parts[2]
            elif name == 'TEL':
                card['phone'].append(value)
            elif name == 'EMAIL':
                card['email'].append(value)
            elif name == 'ORG':
                card['company'] = value.split(';')[0]
            elif name == 'TITLE':
                card['position'] = value
            elif name == 'NOTE':
                card['notes'] = value
            elif name == 'CATEGORIES':
                card['tags'] += [t.strip() for t in value.split(',') if t.strip()]
    return cards


# ---- normalisation ----
SPLIT = re.compile(r'\s*(?::::|;|\n|\||/|,)\s*')


TAG_SPLIT = re.compile(r'\s*(?::::|;|\n|,)\s*')


def split_values(value, pattern=SPLIT):
    return [part.strip() for part in pattern.split(str(value or '')) if part.strip()]


def normalize_phone(raw, default_ddd=''):
    """Returns (e164_digits, kind) where kind is 'mobile' or 'landline'; (None, reason) when unusable."""
    text = str(raw).strip()
    digits = re.sub(r'\D', '', text)
    if len(digits) < 8:
        return None, 'curto'
    international = text.startswith('+')
    if digits.startswith('00'):
        digits, international = digits[2:], True
    elif digits.startswith('0') and not international:
        digits = digits.lstrip('0')
        if len(digits) > 11 and not digits.startswith('55'):
            digits = digits[2:]  # carrier prefix, e.g. 0 21 + number
    if international or (digits.startswith('55') and len(digits) in (12, 13)):
        if not 8 <= len(digits) <= 15:
            return None, 'inválido'
        if digits.startswith('55') and len(digits) == 12 and digits[4] in '6789':
            digits = digits[:4] + '9' + digits[4:]
        national = digits[2:] if digits.startswith('55') else digits
        kind = 'mobile' if digits.startswith('55') and len(national) == 11 and national[2] == '9' else 'landline'
        return '+' + digits, kind
    if len(digits) in (8, 9):
        if not default_ddd:
            return None, 'sem DDD'
        digits = re.sub(r'\D', '', default_ddd) + digits
    if len(digits) in (10, 11):
        if len(digits) == 10 and digits[2] in '6789':
            digits = digits[:2] + '9' + digits[2:]  # pre-2012 mobile numbers gained a ninth digit
        kind = 'mobile' if len(digits) == 11 and digits[2] == '9' else 'landline'
        return '+55' + digits, kind
    return None, 'inválido'


def pick_phones(values, default_ddd=''):
    found, rejected = [], []
    for value in values:
        for piece in split_values(value):
            number, kind = normalize_phone(piece, default_ddd)
            if number:
                if number not in [n for n, _ in found]:
                    found.append((number, kind))
            else:
                rejected.append(kind)
    found.sort(key=lambda item: item[1] != 'mobile')  # stable: mobile numbers first (WhatsApp)
    return [n for n, _ in found], rejected


EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def pick_emails(values):
    out = []
    for value in values:
        for piece in split_values(value):
            piece = piece.strip().lower()
            if EMAIL.match(piece) and piece not in out and len(piece) <= 254:
                out.append(piece)
    return out


def build_name(rec):
    full = ' '.join(
        str(rec.get(k, '')).strip() for k in ('first_name', 'middle_name', 'last_name') if str(rec.get(k, '')).strip()
    )
    name = full or str(rec.get('full_name', '')).strip() or str(rec.get('company', '')).strip()
    name = re.sub(r'\s+', ' ', name)
    return '' if not re.search(r'[A-Za-zÀ-ÿ0-9]', name) else name[:180]


def to_records(text, fmt, headers, rows, mapping):
    """Neutral records: {name?, emails[], phones[], company, position, notes, source, tags[]} plus the file line number."""
    if fmt == 'vcard':
        yield from enumerate(read_vcard(text), 1)
        return
    index_of = {h: i for i, h in enumerate(headers)}
    for line, row in enumerate(rows, 2):
        rec = {}
        for key, cols in mapping.items():
            values = [
                row[index_of[c]].strip()
                for c in cols
                if c in index_of and index_of[c] < len(row) and row[index_of[c]].strip()
            ]
            if not values:
                continue
            rec[key] = values if key in MULTI else values[0]
        yield line, rec


def process(text, fmt, headers, rows, mapping, options, existing_phones, existing_emails):
    """Normalises and de-duplicates. Returns (records, summary)."""
    default_ddd = (options.get('default_ddd') or '').strip()
    ignored = set(options.get('ignored_tags') or [])
    use_tags = options.get('import_tags', True)
    records, labels = [], {}
    summary = {
        'total': 0,
        'valid': 0,
        'with_phone': 0,
        'with_email': 0,
        'invalid': 0,
        'duplicates': 0,
        'rejected_phones': {},
        'problems': [],
    }
    seen_phones, seen_emails = set(), set()
    for line, rec in to_records(text, fmt, headers, rows, mapping):
        summary['total'] += 1
        if summary['total'] > MAX_ROWS:
            raise ValueError(f'Importe até {MAX_ROWS:,} contatos por vez.'.replace(',', '.'))
        phones, rejected = pick_phones(
            rec.get('phone', []) if isinstance(rec.get('phone'), list) else [rec.get('phone', '')], default_ddd
        )
        for reason in rejected:
            summary['rejected_phones'][reason] = summary['rejected_phones'].get(reason, 0) + 1
        emails = pick_emails(rec.get('email', []) if isinstance(rec.get('email'), list) else [rec.get('email', '')])
        tags = []
        for raw in rec.get('tags') or []:
            for tag in split_values(raw, TAG_SPLIT):
                labels[tag] = labels.get(tag, 0) + 1
                if use_tags and tag not in ignored and tag not in tags and not tag.startswith('*'):
                    tags.append(tag[:80])
        name = build_name(rec) or (phones[0] if phones else (emails[0] if emails else ''))
        if not name or (not phones and not emails and not options.get('allow_without_contact')):
            summary['invalid'] += 1
            if len(summary['problems']) < 20:
                summary['problems'].append(
                    {'line': line, 'reason': 'Sem nome' if not name else 'Sem telefone ou e-mail válido'}
                )
            continue
        duplicate = (
            (phones and phones[0] in existing_phones)
            or (emails and emails[0] in existing_emails)
            or (phones and phones[0] in seen_phones)
            or (emails and emails[0] in seen_emails)
        )
        if phones:
            seen_phones.add(phones[0])
        if emails:
            seen_emails.add(emails[0])
        summary['valid'] += 1
        summary['with_phone'] += bool(phones)
        summary['with_email'] += bool(emails)
        records.append(
            {
                'line': line,
                'name': name,
                'phones': phones,
                'emails': emails,
                'company': str(rec.get('company', '') or '').strip()[:150],
                'position': str(rec.get('position', '') or '').strip()[:120],
                'notes': str(rec.get('notes', '') or '').strip()[:5000],
                'source': (str(rec.get('source', '') or '').strip() or options.get('source') or 'Importação')[:100],
                'tags': tags,
                'duplicate': bool(duplicate),
            }
        )
        if duplicate:
            summary['duplicates'] += 1
    summary['labels'] = sorted(({'label': k, 'count': v} for k, v in labels.items()), key=lambda x: -x['count'])[:30]
    return records, summary


def load(content, filename, mapping=None):
    """Parses the upload and returns (text, format, headers, rows, mapping)."""
    text = content if isinstance(content, str) else decode(content)
    if text.lstrip().upper().startswith('BEGIN:VCARD'):
        return text, 'vcard', [], [], {}
    headers, rows = read_csv(text)
    if not headers:
        raise ValueError('O arquivo está vazio.')
    if len(set(headers)) != len(headers):  # keep duplicate headers addressable
        seen = {}
        fixed = []
        for h in headers:
            seen[h] = seen.get(h, 0) + 1
            fixed.append(h if seen[h] == 1 else f'{h} ({seen[h]})')
        headers = fixed
    fmt = detect_format(text, headers)
    return text, fmt, headers, rows, (mapping or suggest_mapping(headers))


def existing_keys(workspace_id):
    phones, emails = set(), set()
    for contact in (
        Contact.query.filter_by(workspace_id=workspace_id, archived=False)
        .with_entities(Contact.phone, Contact.email)
        .all()
    ):
        if contact.phone:
            number, _ = normalize_phone(contact.phone, '')
            if number:
                phones.add(number)
            digits = re.sub(r'\D', '', contact.phone)
            if digits:
                phones.add('+' + digits)
                phones.add('+55' + digits)
        if contact.email:
            emails.add(contact.email.lower())
    return phones, emails
