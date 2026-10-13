# novelSkill
소설 작성 및 소설 책 제작 Skill

**Novel Book Studio · 소설책 제작 스킬**

애니메이션풍 삽화 소설, 세로 웹툰, 만화 PDF/CBZ를 지원합니다. 삽화 소설의 장면 그림은 **왼쪽 본문과 마주 보는 오른쪽 독립 한 페이지**를 사용합니다. 모든 권과 파생 형식은 하나의 캐릭터 기준을 공유합니다. 실제 애니메이션 영상 생성 기능은 포함하지 않습니다.

## 전면 삽화와 캐릭터 일관성

`character-bible.json`은 화풍·고정 외양·복장·기준 그림의 공통 원장입니다. 각 권/각색본의 `production.json`은 원고, 장면 발췌, 화면에 나오는 인물의 현재 상태, 프롬프트, 그림, 검수 기록을 연결합니다. 원고·기준·상태·그림이 바뀌면 오래된 검수로 최종 출력할 수 없습니다. 해시 검사는 얼굴 일치나 그림의 의미를 자동 판정하지 않으므로 실제 이미지를 보며 검수해야 합니다.

```bash
python skills/novel-book-writer/scripts/story_project.py init \
  --project output/my-story --title '새 이야기' --parts 3 --format illustrated-novel
python skills/novel-book-writer/scripts/story_project.py status --project output/my-story
```

생성 결과는 제작 골격이며 원고나 그림이 완성된 상태가 아닙니다. 실제 원고 문단 사이에 `[[art:scene-id]]`를 넣고 계획 파일을 작성합니다. `--visual-plan`을 지정한 빌더는 삽화 쪽·목차·링크를 함께 조판합니다. `--allow-pending-art`는 위치 점검 초안이며, 최종 출력에서는 오른쪽 삽화의 맞은편에 실제 장면 발췌가 있어야 합니다. 빈 왼쪽 쪽이나 엉뚱한 장면은 거부하므로 초안에서 앵커 위치를 조정합니다.

```bash
python skills/novel-book-writer/scripts/build_book.py \
  --manuscript output/my-story/volumes/part-01/manuscript.md \
  --visual-plan output/my-story/volumes/part-01/production.json \
  --output output/my-story/output/part-01.pdf --title '새 이야기 1부' --author 'AI 창작'
```

PDF는 표지=1쪽, 왼쪽 짝수/오른쪽 홀수 기준입니다. 뷰어에서 두 페이지 보기와 표지 단독 표시를 켭니다. 원고를 다시 조판하므로 실제 쪽수와 목차도 갱신됩니다. 하단 삽화는 기존 작업의 명시적 호환 옵션으로만 유지합니다.

## 웹툰·만화 제작

원고를 패널 대본으로 각색하고 같은 캐릭터 원장을 참조합니다. 검수된 패널과 별도 한글 말풍선을 `build_visual.py`로 합성합니다. `format: webtoon`은 스크롤 HTML/PNG, `format: comic`은 A5 PDF/150dpi PNG/CBZ를 만듭니다. 웹툰은 패널 사이에서만 구간을 나누며, 만화는 LTR/RTL과 패널 좌표를 명시합니다. 기존 출력 폴더는 덮지 않습니다.

```bash
python skills/novel-book-writer/scripts/build_visual.py \
  --plan /path/to/adaptation/production.json --output /path/to/output/webtoon-v1
```

현재 말풍선은 둥근 사각형이며 자동 꼬리·손글씨 효과음·영상 애니메이션은 지원하지 않습니다. 최종 구도와 읽기 순서는 사람이거나 이미지 보는 에이전트가 확인해야 합니다. 인쇄소 납품 규격과 플랫폼 업로드 규격은 별도입니다.

- [실행 JSON·명령](skills/novel-book-writer/references/visual-plan.md)
- [캐릭터 기준과 생성·검수](skills/novel-book-writer/references/character-consistency.md)
- [오른쪽 전면 삽화 제작](skills/novel-book-writer/references/production-loop.md)
- [웹툰·만화 각색](skills/novel-book-writer/references/visual-formats.md)

비슷한 장르 작품의 기법을 참고해 독창적인 한국어 소설을 쓰고, 인물의 선택과 사건의 인과관계를 검토하고 가독성을 교정한 뒤 표지·목차·본문이 있는 PDF 책으로 제작하는 재사용 스킬입니다.

**장르 참고 → 이야기 설계 → 장별 집필 → 본문 단독 이해도 검사 → 가독성 교정 → 표지 디자인·PDF 검증**을 다룹니다. 기존 TRPG 각색 지침을 일반 소설에도 적용할 수 있게 발전시켰습니다. '학습'은 실제 열람 자료를 분석하는 과정이며 모델 훈련이 아닙니다.

## 설치

이 저장소의 `skills/novel-book-writer` 폴더 전체를 사용하는 에이전트의 스킬 경로에 복사합니다. 이미 같은 이름의 스킬이 있으면 백업한 뒤 변경점을 비교하세요.

```bash
git clone https://github.com/no1fc/novel-book-studio.git
cd novel-book-studio
mkdir -p ~/.codex/skills
cp -R skills/novel-book-writer ~/.codex/skills/
```

Codex에서 새 작업을 열고 `$novel-book-writer`로 호출합니다. Claude Code에서는 같은 폴더를 `~/.claude/skills/` 또는 프로젝트 `.claude/skills/`에 넣어 사용할 수 있습니다. SKILL.md를 지원하는 다른 에이전트는 해당 제품의 설치 경로를 사용합니다. 도구·네트워크·PDF 실행 지원은 환경마다 다르며 모든 제품에서의 실행을 검증한 것은 아닙니다.

사용 예:

> $novel-book-writer로 해안 도시를 배경으로 한 미스터리 판타지 소설을 써 줘. 비슷한 장르의 공개 자료를 실제로 확인해 기법을 참고하고, 공백 포함 2만 자 안팎의 완결 본문을 작성해 줘. 인물의 감정과 선택을 자연스럽게 보여 주고, 교정 후 표지·목차·본문 PDF까지 만들어 줘.

> 이 원고의 사건과 결말은 보존하고, 설명이 몰리는 부분과 딱딱한 대화를 고쳐 줘. 중요한 선택 장면을 풍부하게 만든 뒤 새 PDF를 만들어 줘.

## 독자가 처음부터 따라갈 수 있도록

도입에서는 인물의 현재 처지·장소·당장 목적을 파악할 단서를 제공합니다. 새 인물은 이름만 나열하지 않고 역할·관계·행동과 연결해 소개하며, 다시 등장할 때 필요한 기억을 짧게 되짚습니다. 중요한 발견 뒤의 해석과 선택을 다음 장면에 이어 사건 보고처럼 읽히는 전개를 교정합니다.

첫 장면만 읽는 검사와 인물 소개·전환 구간 검사를 완독 후 이해도 검사와 별도로 수행합니다. TRPG 각색에서는 원전의 사실과 인물 보존 조건을 지키면서 반복 탐색·발언 차례·이동 기록을 소설 장면으로 재구성합니다. 인물 수를 일괄 제한하거나 세계관 설명을 앞에 몰아넣는 방식은 사용하지 않습니다. [짧은 소설화 시범](examples/scene-flow-study.md)에서 적용 모습을 확인할 수 있습니다.

## 무엇을 요청해야 할지 모르겠다면

새 대화에서 아래처럼 시작하세요. 이 단계에서는 소설이나 PDF를 바로 만들지 않고, 선택을 돕고 복사 가능한 요청문을 정리합니다.

> novel-book-writer로 어떤 소설을 만들지 같이 정해 줘. 아직 장르나 소재는 모르겠어. 서로 다른 방향을 3개 추천하고 선택을 도와줘.

> novel-book-writer로 제작 요청문을 만들어 줘. 스릴러·추리 중편이고, 표지·속표지·목차 제외, 프롤로그 포함 A4 본문 약 45쪽을 원해. 필요하면 늘려도 돼. 나머지는 추천해 줘. 지금은 요청문만 작성해 줘.

> 이 요청문대로 제작을 시작해 줘.

이미 정한 조건은 다시 묻지 않습니다. 장르·배경·갈등·분량·분위기·결과물을 정리하며, 미정인 설정은 제안으로 구분합니다. 요청문만 필요하면 그 단계에서 끝냅니다. 실제 제작을 요청하면 기존 집필·검토·PDF 절차로 이어집니다. [요청문 만들기 지침](skills/novel-book-writer/references/request-builder.md)을 참고하세요.

**판형 안내:** 현재 번들 PDF 빌더는 A5 고정입니다. A4 요청문도 만들 수 있지만 실제 A4 제작에는 조판 수정 또는 다른 도구가 필요합니다. A4 전환이 구현되어 있다고 간주하거나 A5로 바꾸어 납품하지 않습니다.

## PDF 도구 준비

Python 3.10 이상을 사용합니다. OS별 네이티브 의존성은 [WeasyPrint 공식 설치 안내](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation)를 확인하세요. Linux에는 Pango와 한글 글꼴이 필요합니다. Debian/Ubuntu의 `fonts-noto-cjk`는 사용할 수 있는 한글 글꼴 패키지입니다. 글꼴 자체는 저장소에 포함하지 않습니다.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python skills/novel-book-writer/scripts/build_book.py \
  --manuscript examples/manuscript-revised.md \
  --output output/water-mailbox.pdf \
  --title '물이 빠진 뒤의 우편함' \
  --author 'AI 창작 예제' --subtitle '소설책 제작 스킬 · 짧은 시연'
```

기본 글꼴은 Noto Serif CJK KR입니다. 다른 환경에서는 `--font-file`로 한글을 지원하는 글꼴을 지정하세요. `--help`가 옵션의 기준입니다. 기본 표지는 타이포그래피로 제작합니다. `--genre`로 장르 색을 선택하고, `--cover-image`로 AI 생성 또는 사용 권한이 있는 그림을 넣을 수 있습니다. AI 생성은 사용하는 에이전트의 이미지 도구가 담당하며 PDF 빌더는 모델을 호출하지 않습니다.

빌더는 제한된 Markdown 원고를 받습니다. 장 제목은 `##`, 문단은 빈 줄, 장면 전환은 `***`를 사용합니다. 수동 목차는 넣지 않습니다. 원고→PDF 도구는 원고를 대신 집필하거나 문학적 완성도를 판정하지 않습니다.

## 구성

- [SKILL.md](skills/novel-book-writer/SKILL.md): 에이전트가 읽는 진입점
- `references/`: 참고 자료 분석, 창작, 교정, 각색, PDF 제작 지침
- `scripts/build_book.py`: 재사용 PDF 제작 도구
- [개정 창작 예제](examples/manuscript-revised.md), [개정 PDF](examples/water-mailbox-revised.pdf), [이해도 개선 기록](examples/comprehension-revision.md)
- [작법·표지 참고 범위](docs/writing-reference.md)
- 이전 원고와 PDF는 비교용으로 보존했습니다. 사건 이해에 문제가 확인되어 현재 권장 예제는 개정본입니다.
- [검증 기록](docs/validation.md): 실제 실행 범위와 미검증 사항

기본 완성물은 원고, 독서용 PDF, 참고 목록, 집필·검토 메모입니다. 장편은 장별로 진행 상황을 저장합니다. 짧은 시범이나 개정만 요청하면 불필요한 책 전체 제작을 강요하지 않습니다.

## 검증

```bash
python -m unittest discover -s tests -v
```

설정집 없이 원고만 읽고 목표·선택 이유·사건 조건·결말의 변화를 본문 근거로 설명하는 검사를 먼저 수행합니다. 중요한 인과가 불명확하면 원고를 수정한 뒤 최종 PDF를 제작합니다. 독립 AI 검사는 사람 독자의 감상 평가와 다릅니다. PDF 텍스트 검사와 실제 렌더링도 함께 수행해야 합니다. PDF가 생성됐다는 사실만으로 시각 검토가 완료된 것은 아닙니다. 인쇄소 납품 규격은 별도 확인이 필요합니다.

## 공개 범위와 이용

저장소에는 스킬, 도구, 새로 작성한 창작 예제만 포함합니다. 사용자의 비공개 원고, 타 작품 원문, 인증정보, 폰트 파일은 포함하지 않습니다. 참고 작품은 링크와 분석 메모로 기록합니다. 이용 조건은 [LICENSE](LICENSE)를 참고하세요.

## 장르 색감과 AI 표지

`--genre mystery|fantasy|romance|horror|sf|literary|classic`으로 시작 팔레트를 선택합니다. 표지·장 제목·본문·종이색을 역할별로 지정할 수 있으며 낮은 글자 대비를 검사합니다. 장르의 고정 규칙이 아니라 작품의 정서에 맞춰 조정할 출발점입니다.

```bash
python skills/novel-book-writer/scripts/build_book.py \
  --manuscript examples/manuscript-revised.md --output output/illustrated-book.pdf \
  --title '물이 빠진 뒤의 우편함' --author 'AI 창작 예제' \
  --genre mystery --cover-image examples/cover-coastal.png
```

`--cover-background`, `--cover-text-color`, `--accent-color`, `--heading-color`, `--text-color`, `--paper-color`는 `'#RRGGBB'`로 덮어쓸 수 있습니다. 지원 이미지는 로컬 PNG/JPEG/WebP입니다. `--cover-layout auto|fullbleed|framed|typographic`으로 구도를 고릅니다. 기본값 `auto`는 이미지가 있으면 전면 삽화, 없으면 타이포그래피입니다. 전면 삽화의 제목은 `--cover-title-position top|center|bottom`으로 실제 글자로 배치합니다. 기본값은 그림 위 직접 조판이며 패널 배경은 `--cover-text-treatment panel`로 선택합니다. `--cover-title-lines '물이 빠진 뒤의|우편함'`처럼 최대 4행으로 나눌 수 있습니다. 실제 표지를 크게·작게 렌더링해 제목과 그림의 관계를 확인해야 합니다.

[표지 제작 지침](skills/novel-book-writer/references/cover-design.md)과 [AI 표지 제작 기록](examples/cover-design.md)을 참고하세요. 이미지 생성은 에이전트의 실제 이미지 도구가 담당하며 이 CLI는 모델을 호출하지 않습니다. 검증용 단색 이미지를 완성 삽화로 납품하지 않습니다.
