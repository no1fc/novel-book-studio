# AI 표지 제작 기록

2026-09-21. 작품: `manuscript.md`, 「물이 빠진 뒤의 우편함」.

- 도구: Codex 내장 ImageGen. 별도 API/CLI를 호출하지 않았다.
- 파일: `cover-coastal.png`, 1024×1536. AI 생성 그림 1회; 원본의 복사본을 사용했다.
- 정서: 조용하고 쓸쓸하지만 다정한 해안 도시 미스터리 판타지.
- 모티프: 썰물 뒤의 골목, 낡은 우편함과 편지. 등장인물의 얼굴이나 결말을 묘사하지 않는다.
- 팔레트: 표지 `#172b35`, 표지 글자 `#edf4ef`, 장식 `#c8a568`, 장 제목 `#28505a`, 본문 `#26353a`, 종이 `#fafbf8`.
- 배치: 이미지 비율을 유지하는 독립 영역과 그 아래의 실제 한글 제목·부제·저자. 이미지 내부에는 글자를 생성하지 않았다.
- 확인: 원고의 해안·우편 모티프와 일치, 의도치 않은 글자/로고 없음, 표지 그림 포함·제목 가독성·본문 대비와 PDF 렌더링 검토.
- 원본 그림 SHA-256: `b9af50dd7d579ffac39172523cb5b99bfa82c04c46172db026b61281413b75fc`.
- 결과: [AI 삽화 적용 PDF](water-mailbox-illustrated.pdf). 기존 타이포그래피 시연본은 별도 보존.

## 실제 생성 프롬프트

```text
Use case: illustration-story. Create an original cover illustration for a Korean quiet coastal mystery-fantasy short novel titled '물이 빠진 뒤의 우편함', but DO NOT include any lettering, typography, logo, watermark or book mockup. Portrait 1024x1536. Scene: an old Korean coastal alley at low tide in the early morning, a small worn tin mailbox hangs near a weathered sea-green doorway, a single cream envelope visible at its slot, wet stone paving and a narrow glimpse of the receding sea. No people. Atmospheric, intimate, wistful but gently hopeful, believable tactile salt and peeling paint, painterly literary editorial illustration with fine brush texture, soft mist, muted midnight navy and sea teal with small warm amber reflected light. Focus on mailbox and envelope in lower-middle part. Upper quarter quiet misty negative space. No supernatural figures, no dramatic horror, no extra story symbols. A flat illustration ready to be used in a book cover design; leave typography to the PDF layout.
```
