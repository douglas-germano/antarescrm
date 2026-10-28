from flask import request
from sqlalchemy import func

from ..extensions import db

_ACCENTS = 'áàâãäéèêëíìîïóòôõöúùûüçñ'
_PLAIN = 'aaaaaeeeeiiiiooooouuuucn'


def fold(text):
    """Lower-case without accents, so "joao" finds "João"."""
    return str(text).lower().translate(str.maketrans(_ACCENTS, _PLAIN))


def search(q, model, *columns):
    term = (request.args.get('search') or '').strip()
    if not term:
        return q
    postgres = db.session.get_bind().dialect.name == 'postgresql'
    folded = '%' + fold(term) + '%'
    clauses = []
    for name in columns:
        column = getattr(model, name)
        clauses.append(
            func.translate(func.lower(column), _ACCENTS, _PLAIN).ilike(folded)
            if postgres
            else column.ilike('%' + term + '%')
        )
    digits = ''.join(ch for ch in term if ch.isdigit())
    if len(digits) >= 3 and 'phone' in columns:  # "(66) 99649-9089" matches +5566996499089
        phone = model.phone
        clauses.append(
            func.regexp_replace(phone, r'\D', '', 'g').ilike('%' + digits + '%')
            if postgres
            else phone.ilike('%' + digits + '%')
        )
    return q.filter(db.or_(*clauses))


def search_columns(q, term, columns, phone=None):
    """Match each word across related fields, preserving page-search semantics in SQL."""
    postgres = db.session.get_bind().dialect.name == 'postgresql'
    for word in term.split():
        clauses = []
        for column in columns:
            value = func.translate(func.lower(column), _ACCENTS, _PLAIN) if postgres else func.lower(column)
            clauses.append(value.contains(fold(word), autoescape=True))
        digits = ''.join(character for character in word if character.isdigit())
        if phone is not None and len(digits) >= 3:
            normalized = func.regexp_replace(phone, r'\D', '', 'g') if postgres else phone
            clauses.append(normalized.contains(digits, autoescape=True))
        q = q.filter(db.or_(*clauses))
    return q
