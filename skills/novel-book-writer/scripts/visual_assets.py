#!/usr/bin/env python3
"""Validate shared character/scene evidence; record an already performed visual review."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from PIL import Image

from page_art import write_atomic

FORMATS = ('illustrated-novel', 'webtoon', 'comic')
ID = re.compile(r'[a-z][a-z0-9_-]{0,63}')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compact(text):
    return re.sub(r'\s+', '', text.replace('*', ''))


def require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be nonempty text')
    return value


def rectangle(value, label):
    if (not isinstance(value, list) or len(value) != 4
            or any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in value)):
        raise ValueError(f'{label}: rect must be [x, y, width, height] fractions')
    x, y, w, h = value
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1.000001 or y + h > 1.000001:
        raise ValueError(f'{label}: rect outside the image/page')
    return value


def local_path(base, value):
    require_text(value, 'local asset path')
    if '://' in value:
        raise ValueError('only explicitly supplied local assets are supported')
    return (base / value).resolve()


def image_bytes(path):
    raw = path.read_bytes()
    with Image.open(path) as image:
        if image.format not in ('PNG', 'JPEG', 'WEBP'):
            raise ValueError(f'unsupported image: {path.name}')
        image.verify()
    return raw


def evidence(plan, shot, base):
    """Bind reviews to all story context, visual state, references and actual pixels."""
    cast = []
    for state in shot['characters']:
        character = next(c for c in plan['characters'] if c['id'] == state['id'])
        cast.append(character)
    payload = {'source': plan['source'], 'format': plan['format'], 'style': plan['style'],
               'characters': cast, 'shot': {k: v for k, v in shot.items() if k != 'review'},
               'image_sha256': digest(image_bytes(local_path(base, shot['image'])))}
    return digest(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode())


def load_plan(path, require_reviews=True, allow_missing_images=False):
    path = Path(path).resolve()
    plan = json.loads(path.read_text(encoding='utf-8'))
    if plan.get('schema_version') != 1 or plan.get('format') not in FORMATS:
        raise ValueError('unsupported visual plan schema_version or format')
    if 'bible' in plan:
        if 'characters' in plan or 'style' in plan:
            raise ValueError('use a shared bible OR inline characters/style, not competing copies')
        bible_path = local_path(path.parent, plan['bible']['path'])
        bible_bytes = bible_path.read_bytes()
        if digest(bible_bytes) != plan['bible']['sha256']:
            raise ValueError('character bible changed; refresh the plan and re-review its shots')
        bible = json.loads(bible_bytes)
        if bible.get('schema_version') != 1:
            raise ValueError('unsupported character bible schema')
        plan['style'], plan['characters'] = bible['style'], bible['characters']
        for character in plan['characters']:
            character['reference']['path'] = str(local_path(bible_path.parent, character['reference']['path']))
    require_text(plan['style'], 'style')
    source = local_path(path.parent, plan['source']['path'])
    source_bytes = source.read_bytes()
    if digest(source_bytes) != plan['source']['sha256']:
        raise ValueError('source changed; update the source hash and re-review affected art')
    manuscript = compact(source_bytes.decode('utf-8-sig'))
    characters = {}
    for character in plan['characters']:
        key = character['id']
        if not ID.fullmatch(key) or key in characters:
            raise ValueError(f'invalid or duplicate character id: {key}')
        require_text(character['name'], f'{key} name')
        if not isinstance(character['invariants'], dict) or not character['invariants']:
            raise ValueError(f'{key}: fixed appearance invariants required')
        if not isinstance(character['outfits'], dict) or not character['outfits']:
            raise ValueError(f'{key}: named outfits required')
        for outfit, description in character['outfits'].items():
            require_text(outfit, f'{key} outfit id')
            require_text(description, f'{key} outfit description')
        ref = character['reference']
        ref_bytes = image_bytes(local_path(path.parent, ref['path']))
        if digest(ref_bytes) != ref['sha256']:
            raise ValueError(f'character reference changed: {key}')
        characters[key] = character
    seen = set()
    if not isinstance(plan['shots'], list) or not plan['shots']:
        raise ValueError('visual plan needs at least one shot')
    for shot in plan['shots']:
        key = shot['id']
        if not ID.fullmatch(key) or key in seen:
            raise ValueError(f'invalid or duplicate shot id: {key}')
        seen.add(key)
        for field in ('excerpt', 'scene', 'prompt', 'image'):
            require_text(shot[field], f'{key} {field}')
        if compact(shot['excerpt']) not in manuscript:
            raise ValueError(f'{key}: excerpt is not in the current source')
        cast = set()
        for state in shot['characters']:
            character = characters.get(state['id'])
            if character is None or state['id'] in cast:
                raise ValueError(f'{key}: unknown or duplicate visible character')
            cast.add(state['id'])
            if state['outfit'] not in character['outfits']:
                raise ValueError(f'{key}: unknown outfit for {state["id"]}')
            require_text(state['state'], f'{key} current character state')
        for bubble in shot.get('dialogue', []):
            require_text(bubble['text'], f'{key} dialogue')
            if bubble.get('speaker') not in cast | {None, 'narrator'}:
                raise ValueError(f'{key}: dialogue speaker is not in the visible cast')
            rectangle(bubble['rect'], f'{key} dialogue')
        asset = local_path(path.parent, shot['image'])
        if allow_missing_images and not asset.exists():
            continue
        current = evidence(plan, shot, path.parent)
        review = shot.get('review', {})
        if require_reviews and (review.get('status') != 'pass' or not review.get('notes', '').strip()
                                or review.get('evidence_sha256') != current):
            raise ValueError(f'pending or stale visual review: {key}')
    return plan


def record_review(path, shot_id, notes):
    require_text(notes, 'review notes')
    path = Path(path).resolve()
    plan = load_plan(path, require_reviews=False, allow_missing_images=True)
    shot = next((s for s in plan['shots'] if s['id'] == shot_id), None)
    if shot is None:
        raise ValueError(f'unknown shot: {shot_id}')
    shot['review'] = {'status': 'pass', 'notes': notes,
                      'evidence_sha256': evidence(plan, shot, path.parent)}
    stored = json.loads(path.read_text(encoding='utf-8'))
    next(s for s in stored['shots'] if s['id'] == shot_id)['review'] = shot['review']
    write_atomic(path, (json.dumps(stored, ensure_ascii=False, indent=2) + '\n').encode())
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('validate', 'record-review'))
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--shot')
    parser.add_argument('--notes', help='Specific observations from an actual visual inspection, not automatic scoring')
    args = parser.parse_args()
    try:
        if args.action == 'record-review':
            if not args.shot or not args.notes:
                parser.error('record-review requires --shot and --notes after viewing the image')
            plan = record_review(args.plan, args.shot, args.notes)
        else:
            plan = load_plan(args.plan)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f'error: {error}\n')
    print(json.dumps({'format': plan['format'], 'shots': len(plan['shots'])}))


if __name__ == '__main__':
    main()
