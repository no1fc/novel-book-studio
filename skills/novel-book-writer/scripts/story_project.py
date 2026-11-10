#!/usr/bin/env python3
"""Create a resumable story project; report actual pending work without marking it complete.

count measures prose the way the skill plans length: characters including
spaces, excluding headings, Markdown marks, art anchors and line breaks.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import tempfile

from visual_assets import FORMATS, digest, load_plan, local_path, require_text

MODES = ('novel',) + FORMATS  # novel: text-only book, no art plan or character art

LEDGER = """# 연속성 원장

본문에 실제로 쓴 사실만 적는다. 계획은 outline.md에 둔다. 장을 완성할 때마다 갱신하고,
다음 장을 쓰기 전에 '현재 상태'와 직전 장 행을 읽는다. 문장으로 띄어 쓰고 약어로 압축하지 않는다.

## 장별 기록

| 권·장 | 작중 날짜·시각(경과일) | 장소 | 일어난 일 한 줄 | 장 끝에서 달라진 것 |
|---|---|---|---|---|

## 현재 상태 (마지막 완성 장의 끝)

- 인물별: 위치 / 부상·몸 상태 / 소지품 / 알고 있는 것과 모르는 것 / 서로의 호칭
- 장소·사물: 방의 수와 구조, 문·열쇠, 남은 식량·연료·돈 등 수량이 있는 것
- 인원: 현재 함께 있는 사람 수와 이름

## 약속과 회수

| 심은 곳(권·장) | 독자가 본 단서·약속 | 회수할 곳 | 상태(미회수/회수/의도적 미해결) |
|---|---|---|---|

## 고정 사항

한 번 본문에 나온 뒤 바뀌면 안 되는 사실: 날짜, 나이, 거리, 이름 표기, 흉터의 좌우, 과거 사건의 순서.
"""

PROGRESS = """# 제작 재개 지점

마지막 갱신: (날짜)

## 지금 상태

- 단계: planning (프로젝트 골격만 생성됨)
- 마지막 완성 장: 없음
- 본문 분량: `story_project.py status`의 실제 수치를 옮겨 적는다

## 다음 작업

1. brief.md와 planning/story-bible.md, planning/outline.md를 작성한다.

## 다음 장 입력

- 목표·시점·장소:
- 직전 장 마지막 상황:
- 이번 장에서 회수하거나 심을 것:

## 미완료·미검증

- 원고, 검토, 조판 전부.

## 재개 명령

세션을 끝내기 전에 위 항목을 현재 사실로 **고쳐 쓴다**. 지난 상태를 아래에 덧붙여 쌓지 않는다.
"""


def count_chars(text):
    """Per-section prose length: spaces count, headings/marks/anchors/newlines do not."""
    sections, current = [], None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('## '):
            current = {'title': stripped[3:].strip(), 'chars': 0}
            sections.append(current)
        elif (stripped and stripped != '***' and not stripped.startswith('# ')
              and not re.fullmatch(r'\[\[art:[a-z0-9_-]+\]\]', stripped)):
            if current is None:
                current = {'title': '(서두)', 'chars': 0}
                sections.append(current)
            current['chars'] += len(stripped.replace('*', ''))
    return {'total_chars': sum(s['chars'] for s in sections), 'sections': sections}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def initialize(project, title, parts=3, mode='illustrated-novel'):
    project = Path(project).resolve()
    if project.exists():
        raise ValueError('project already exists; use status and resume instead of overwriting')
    require_text(title, 'title')
    if not 1 <= parts <= 12 or mode not in MODES:
        raise ValueError('parts must be 1-12 and format must be supported')
    project.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.story-', dir=project.parent))
    try:
        for directory in (('planning', 'qa', 'output') if mode == 'novel'
                          else ('art/characters', 'art/scenes', 'planning', 'qa', 'output')):
            (staging / directory).mkdir(parents=True)
        write_json(staging / 'project.json', {'schema_version': 1, 'title': title, 'format': mode,
            'parts': parts, 'status': 'planning',
            **({} if mode == 'novel' else {'canonical_characters': 'character-bible.json'})})
        if mode != 'novel':
            write_json(staging / 'character-bible.json', {'schema_version': 1,
                'style': '제작 브리프에 맞춰 화풍·선·명암·색·체형 비율을 구체화한다. 기준 그림은 확보한 경로로 마련한다.',
                'characters': []})
        (staging / 'brief.md').write_text(f'# {title}\n\n형식: {mode}\n구성: {parts}부\n\n'
            '사용자 확정 조건과 제작자 제안을 구분해 기록한다. 분량은 공백 포함 본문 문자 수로 관리한다.\n')
        (staging / 'planning/story-bible.md').write_text('# 이야기 원장\n\n'
            '인물의 욕망·관계, 세계 규칙과 대가, 실제 연표/제시 순서, 복선과 회수, 권간 연속성을 기록한다.\n')
        (staging / 'planning/outline.md').write_text('# 장면 설계\n\n'
            '각 장: 시점 / 장소·시간 / 목표 / 장애 / 선택 / 결과 / 관계 변화 / 다음 장 연결.\n')
        (staging / 'planning/continuity.md').write_text(LEDGER, encoding='utf-8')
        (staging / 'progress.md').write_text(PROGRESS, encoding='utf-8')
        for part in range(1, parts + 1):
            folder = staging / f'volumes/part-{part:02}'
            (folder / 'chapters').mkdir(parents=True)
            source = folder / 'manuscript.md'
            source.write_text(f'# {title} · {part}부\n', encoding='utf-8')
            if mode == 'novel':
                continue
            layout = ({'sequence': [], 'width_px': 800, 'max_slice_height_px': 2400, 'gap_px': 80}
                      if mode == 'webtoon' else {'reading_direction': 'ltr', 'pages': []} if mode == 'comic' else None)
            plan = {'schema_version': 1, 'format': mode,
                'source': {'path': 'manuscript.md', 'sha256': digest(source.read_bytes())},
                'bible': {'path': '../../character-bible.json', 'sha256': digest((staging / 'character-bible.json').read_bytes())},
                'shots': []}
            if layout is not None:
                plan['layout'] = layout
            write_json(folder / 'production.json', plan)
        staging.rename(project)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return status(project)


def status(project):
    project = Path(project).resolve()
    settings = json.loads((project / 'project.json').read_text())
    volumes = []
    for part in range(1, settings['parts'] + 1):
        folder = project / f'volumes/part-{part:02}'
        path = folder / 'production.json'
        prose = count_chars((folder / 'manuscript.md').read_text(encoding='utf-8-sig'))
        if not path.exists():
            state = {'asset_status': 'none (text-only)'}
        else:
            try:
                plan = load_plan(path)
                state = {'asset_status': 'reviewed', 'shots': len(plan['shots']),
                         'remaining': 'Final composition and visual/content QA must be checked separately.'}
            except (ValueError, OSError, KeyError, TypeError) as error:
                state = {'asset_status': 'pending', 'reason': str(error)}
                try:  # Name the files still to be made or imported.
                    draft = load_plan(path, require_reviews=False, allow_missing_images=True)
                    wanted = [c['reference']['path'] for c in draft['characters']] + [s['image'] for s in draft['shots']]
                    state['missing_art'] = [str(f) for f in (local_path(folder, w) for w in wanted) if not f.exists()]
                except (ValueError, OSError, KeyError, TypeError):
                    pass
        volumes.append({'part': part, 'total_chars': prose['total_chars'],
                        'chapters': prose['sections'], **state})
    return {'title': settings['title'], 'recorded_status': settings['status'],
            'resume_notes': str(project / 'progress.md'),
            'continuity_ledger': str(project / 'planning/continuity.md'),
            'total_chars': sum(v['total_chars'] for v in volumes), 'volumes': volumes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'status', 'count'))
    parser.add_argument('--project', type=Path, help='init/status: project folder')
    parser.add_argument('--manuscript', type=Path, help='count: any manuscript file, with or without a project')
    parser.add_argument('--title')
    parser.add_argument('--parts', type=int, default=3)
    parser.add_argument('--format', choices=MODES, default='illustrated-novel')
    args = parser.parse_args()
    if not (args.manuscript if args.action == 'count' else args.project):
        parser.error('count requires --manuscript; init and status require --project')
    try:
        result = (initialize(args.project, args.title, args.parts, args.format) if args.action == 'init'
                  else count_chars(args.manuscript.read_text(encoding='utf-8-sig')) if args.action == 'count'
                  else status(args.project))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f'error: {error}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
