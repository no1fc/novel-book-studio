# 실행 계획 JSON과 명령

경로는 해당 JSON 파일의 위치를 기준으로 해석한다. `source.path`는 현재 원고 또는 패널 대본, `bible.path`는 공통 캐릭터 원장이다. 원고·원장·기준 그림의 해시는 실제 파일 바이트의 SHA-256이다. 해시를 업데이트하는 행위는 검수 통과가 아니다.

## 프로젝트 생성 및 재개

아래 명령의 `scripts/`는 설치된 스킬 폴더 기준이다. 실행 환경에 WeasyPrint 70.0, pypdf, PyMuPDF, Pillow, 한글 글꼴이 필요하다. 저장소 `requirements.txt`를 우선 사용한다.

```bash
python scripts/story_project.py init --project /path/to/book --title '작품 제목' --parts 3 --format illustrated-novel
python scripts/story_project.py status --project /path/to/book
```

`init`은 존재하는 프로젝트를 덮지 않는다. 생성된 원고에는 제목만 있고 기준 인물/그림/장면은 아직 없다. `status`는 검수 상태를 진단할 뿐 작품 완결이나 최종 시각 검수 완료를 선언하지 않는다. `progress.md`를 매 집필·개정·그림 제작 단계 후 갱신한다.

## 공통 character-bible.json

아래 예의 해시는 실제 파일에서 계산해 넣는다. `reference.path`는 bible 위치 기준이다. 한 작품 안에서는 같은 ID를 다른 인물에게 재사용하지 않는다.

```json
{
  "schema_version": 1,
  "style": "2D 애니메이션풍, 또렷한 선, 절제한 셀 명암, 자연스러운 성인 비율, 차분한 숲색과 따뜻한 피부색",
  "characters": [{
    "id": "ian",
    "name": "이안",
    "invariants": {
      "age": "외형 22세",
      "hair": "검은 짧은 머리, 캐릭터의 왼쪽 가르마",
      "eyes": "짙은 갈색, 길고 차분한 눈매",
      "build": "마른 잔근육, 178cm",
      "marks": "얼굴 흉터 없음"
    },
    "outfits": {
      "village": "크림색 린넨 셔츠, 짙은 갈색 바지와 작업화",
      "travel": "village 위 짙은 녹색 짧은 망토, 갈색 여행 가방"
    },
    "reference": {"path": "art/characters/ian-v1.png", "sha256": "실제 기준 파일의 SHA-256"}
  }]
}
```

## 권별 production.json

아래는 실행 계약을 보여 주는 예다. 이미지와 원고를 실제 작성하고 해시를 채워야 실행된다. 원장과 계획에서 `style`/`characters`를 중복하지 않는다. 단편 독립 계획에 한해 `bible` 대신 인라인 `style`/`characters`를 사용할 수 있다.

```json
{
  "schema_version": 1,
  "format": "illustrated-novel",
  "source": {"path": "manuscript.md", "sha256": "실제 원고의 SHA-256"},
  "bible": {"path": "../../character-bible.json", "sha256": "실제 원장의 SHA-256"},
  "shots": [{
    "id": "p1-bridge",
    "excerpt": "이안은 아이를 등 뒤로 물리고 도끼를 들었다.",
    "scene": "해 질 무렵 숲의 부러진 다리. 이안이 마물과 아이 사이를 막는 순간.",
    "characters": [{"id": "ian", "outfit": "village", "state": "오른손 도끼, 소매 걷음, 부상 없음"}],
    "prompt": "A5 portrait full-page anime-style scene. Use the supplied Ian reference sheet; preserve face, hair and clothing. Ian guards the bridge with an axe in his right hand. Keep face, hands and axe within safe edges. No text or watermark. Other visible characters require their own planned references.",
    "image": "../../art/scenes/p1-bridge-v1.png",
    "dialogue": [],
    "review": {"status": "pending", "notes": ""}
  }]
}
```

`scene`와 화면의 인물이 모두 `characters`에 있어야 한다. 예처럼 아이가 프레임 밖에 있으면 상태/구도에 명시한다. 프레임 안으로 옮기면 아이의 기준과 상태를 추가한다. `excerpt`는 실제 원고에서 복사하며 소설 최종 출력에서는 맞은편 왼쪽 페이지에도 있어야 한다.

검수 증거 해시는 현재 전체 원고 해시, 형식, 화풍, 등장인물 고정 설정·복장·기준 그림, 장면 상태·프롬프트·대사, 실제 그림 바이트를 묶는다. 이들 중 하나라도 바뀌면 기존 검수로 출력할 수 없다. bible 자체가 바뀌면 연결된 계획의 bible 해시를 갱신하고 다시 검수한다. 해시는 자동 얼굴 일치 점수가 아니다.

## 소설 제작 명령

원고의 해당 문단 뒤 한 줄에 `[[art:p1-bridge]]`를 둔다. 각 shot은 정확히 한 번 등장해야 한다. 모든 prose는 `## 장 제목` 아래에 둔다.

```bash
python scripts/build_book.py --manuscript /path/to/book/volumes/part-01/manuscript.md --output /path/to/book/output/part-01-draft.pdf --title '작품 제목 1부' --author 'AI 창작' --visual-plan /path/to/book/volumes/part-01/production.json --allow-pending-art

# 먼저 실제 그림과 기준을 직접 확인한 뒤 관찰 내용을 적는다.
python scripts/visual_assets.py record-review --plan /path/to/book/volumes/part-01/production.json --shot p1-bridge --notes '기준 시트와 눈매·가르마·복장 일치. 오른손 도끼와 원고의 부상 없음 확인. 다음 사건 노출 없음.'
python scripts/visual_assets.py validate --plan /path/to/book/volumes/part-01/production.json
python scripts/build_book.py --manuscript /path/to/book/volumes/part-01/manuscript.md --output /path/to/book/output/part-01-final.pdf --title '작품 제목 1부' --author 'AI 창작' --visual-plan /path/to/book/volumes/part-01/production.json
```

저자 표기는 사용자가 정한 것을 우선한다. 예의 AI 표기는 실행 예이며 실존 작가명이나 출판사를 꾸미지 않는다. 빌더는 원고·기준·계획을 덮는 출력을 거부한다. 검증 실패 시 기존 PDF를 보존한다. 성공 시 같은 출력 경로는 갱신되므로 최종본을 보존하려면 버전별 파일명을 쓴다.

## 웹툰·만화 계획

각색 대본을 `source`로 두고 패널마다 shot을 작성한다. 전체 등장인물은 같은 bible을 참조한다. 패널 ID는 중복하지 않으며 레이아웃에 모든 shot을 정확히 한 번 넣는다. 같은 그림을 정당하게 재사용하더라도 별도 행동 단위는 별도 ID로 기록한다.

웹툰의 추가 필드:

```json
{"format":"webtoon", "layout":{"sequence":["p1-bridge"], "width_px":800, "max_slice_height_px":2400, "gap_px":80}}
```

만화의 추가 필드:

```json
{"format":"comic", "layout":{"reading_direction":"ltr", "pages":[{"panels":[{"shot":"p1-bridge", "rect":[0.06,0.05,0.88,0.90]}]}]}}
```

말풍선은 shot의 `dialogue`에 넣는다. `rect`는 해당 패널 이미지의 비율이며 만화 페이지 전체 좌표와 구분한다. narration은 `speaker: "narrator"`, 나머지는 화면에 있는 캐릭터 ID를 쓴다. 현재 렌더러에서 화면 밖 화자의 말은 지문으로 각색하거나 그 화자의 패널을 추가한다.

```json
{"speaker":"ian", "text":"내 뒤에 있어.", "rect":[0.08,0.05,0.70,0.15], "font_size_px":22}
```

```bash
python scripts/build_visual.py --plan /path/to/webtoon/production.json --output /path/to/output/webtoon-v1
python scripts/build_visual.py --plan /path/to/comic/production.json --output /path/to/output/comic-v1
```

출력 폴더가 이미 있으면 보존을 위해 거부한다. 새 버전 폴더를 사용한다. 모든 그림 검수, 패널 사각형, 말풍선 수용 여부를 확인한 다음 임시 폴더에서 완성한 결과만 전달한다. 최종 렌더링 검수는 별도로 수행한다.
