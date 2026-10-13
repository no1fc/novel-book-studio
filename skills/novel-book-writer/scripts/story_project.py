#!/usr/bin/env python3
"""Create a resumable story project; report actual pending work without marking it complete."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from visual_assets import FORMATS, digest, load_plan, require_text


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def initialize(project, title, parts=3, mode='illustrated-novel'):
    project = Path(project).resolve()
    if project.exists():
        raise ValueError('project already exists; use status and resume instead of overwriting')
    require_text(title, 'title')
    if not 1 <= parts <= 12 or mode not in FORMATS:
        raise ValueError('parts must be 1-12 and format must be supported')
    project.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.story-', dir=project.parent))
    try:
        for directory in ('art/characters', 'art/scenes', 'planning', 'qa', 'output'):
            (staging / directory).mkdir(parents=True)
        write_json(staging / 'project.json', {'schema_version': 1, 'title': title, 'format': mode,
            'parts': parts, 'status': 'planning', 'canonical_characters': 'character-bible.json'})
        write_json(staging / 'character-bible.json', {'schema_version': 1,
            'style': '제작 브리프에 맞춰 화풍·선·명암·색·체형 비율을 구체화하고 기준 그림을 생성한다.',
            'characters': []})
        (staging / 'brief.md').write_text(f'# {title}\n\n형식: {mode}\n구성: {parts}부\n\n'
            '사용자 확정 조건과 제작자 제안을 구분해 기록한다. 분량은 공백 포함 본문 문자 수로 관리한다.\n')
        (staging / 'planning/story-bible.md').write_text('# 이야기 원장\n\n'
            '인물의 욕망·관계, 세계 규칙과 대가, 실제 연표/제시 순서, 복선과 회수, 권간 연속성을 기록한다.\n')
        (staging / 'planning/outline.md').write_text('# 장면 설계\n\n'
            '각 장: 시점 / 장소·시간 / 목표 / 장애 / 선택 / 결과 / 관계 변화 / 다음 장 연결.\n')
        (staging / 'progress.md').write_text('# 제작 재개 지점\n\n'
            '- 상태: planning (프로젝트 골격만 생성됨)\n- 마지막 완성 장: 없음\n'
            '- 다음 작업: brief.md와 이야기/캐릭터 기준을 작성하고 기준 이미지를 제작한다.\n'
            '- 미완료: 원고, 기준 그림, 장면 그림, 검수, 최종 조판 전부.\n\n'
            '세션 종료 전 마지막 완성 파일·다음 장 목표·미해결 문제·실행 명령을 갱신한다.\n')
        for part in range(1, parts + 1):
            folder = staging / f'volumes/part-{part:02}'
            (folder / 'chapters').mkdir(parents=True)
            source = folder / 'manuscript.md'
            source.write_text(f'# {title} · {part}부\n', encoding='utf-8')
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
        path = project / f'volumes/part-{part:02}/production.json'
        try:
            plan = load_plan(path)
            state = {'asset_status': 'reviewed', 'shots': len(plan['shots']),
                     'remaining': 'Final composition and visual/content QA must be checked separately.'}
        except (ValueError, OSError, KeyError, TypeError) as error:
            state = {'asset_status': 'pending', 'reason': str(error)}
        volumes.append({'part': part, **state})
    return {'title': settings['title'], 'recorded_status': settings['status'],
            'resume_notes': str(project / 'progress.md'), 'volumes': volumes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'status'))
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--title')
    parser.add_argument('--parts', type=int, default=3)
    parser.add_argument('--format', choices=FORMATS, default='illustrated-novel')
    args = parser.parse_args()
    try:
        result = (initialize(args.project, args.title, args.parts, args.format) if args.action == 'init'
                  else status(args.project))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f'error: {error}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
