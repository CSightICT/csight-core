# CSight 추계 논문 초안 편집 및 제출 메모

2026-10-18 작성. 이 파일은 원고 밖의 인계 메모이며 제출 본문에 포함하지 않는다.

## 전달 파일

- [편집용 DOCX](../../output/papers/CSight_2026_추계_2쪽_논문초안.docx)
- [2쪽 검토용 PDF](../../output/pdf/CSight_2026_추계_2쪽_논문초안.pdf)
- [본문 Markdown](CSight_2026_추계_2쪽_논문초안.md)
- [400 dpi 구조도 PNG](../../output/papers/CSight_시스템구조도.png)

## 적용한 형식과 남은 단계

공식 대학생 양식의 제목·저자·소속·이메일·지도교수와 연구 배경, 연구 내용, 현실적 제한 조건, 기대효과 및 활용, 결론, 참고문헌 순서를 적용했다. 별도 초록·영문제목·쪽번호를 추가하지 않았다. A4, 2단, 단간 8mm, 좌우 20mm, 본문 10pt, 제목 16pt, 장제목 12pt, 캡션 9pt를 적용했다. 한글의 위아래 여백 25mm 및 머리·꼬리 영역 15mm를 Word 본문 위아래 40mm로 대응했다. 본문 행간은 10pt의 160%에 해당하는 16pt 고정값이다.

PDF는 DOCX를 LibreOffice로 렌더링한 검토본이다. 원본 지정 글꼴은 DOCX에 유지했으며, 렌더러에서는 없는 휴먼명조/한컴바탕/휴먼고딕을 한컴 함초롬바탕/돋움으로 대체했다. 참고문헌은 영문 가독성을 위해 자간 0과 왼쪽 정렬을 적용했다. 한글 뷰어에서도 DOCX가 정상 열리고 인쇄 미리보기가 2쪽임을 확인했다. 최종 HWP 저장 후에는 지정 글꼴·단/행간·그림 앞뒤 여백과 두 쪽 유지 여부를 다시 확인한다.

공식 제출 안내는 HWP 파일을 요구한다. 현재 환경의 한컴은 뷰어여서 HWP로 저장할 수 없고, 직접 생성한 HWP 후보는 열람 검증을 통과하지 못했다. 따라서 검증되지 않은 HWP는 납품 파일에 포함하지 않았다. 한글 편집기에서 DOCX를 열어 공식 학생 양식의 글꼴/서식을 확인하고 HWP로 저장하는 단계가 남아 있다. 파일명은 투고자에 따라 `투고자명 - 논문제목.hwp`로 맞춘다. 학회 업로드/접수는 수행하지 않았다.

저자 순서와 이메일은 사용자 제공값을 반영했다. 황세웅 교수는 사용자 지시에 따라 지도교수(교신저자)로 표시했다. 교수의 이메일은 제공되지 않아 만들지 않았으며 제출 폼이 교신 이메일을 요구하면 확인해야 한다. 감사의 글은 실제 지원사업 문구가 제공되지 않아 생략했다.

## 근거와 주장 범위

- 정책 규칙: `evaluation/policy_engine_v1/results/test_metrics.json`, 합성 Test 40건, 규칙 일치율 1.00, 금지 결정 0건.
- 검토 절차: `evaluation/human_review_workflow_v1/results/test_metrics.json`, 합성 Test 30건, 상태·권한·감사 지표 각각 1.00. 실제 사람 30명 실험이 아니다.
- 내부 연결: `docs/progress/TEST_DATA_RESET_2026-09-10.json` 및 `local-data/internal-feedback-reset-20260910/workflow_report.json`, 합성 문의·선별 이미지 10건의 별도 Text-v2 경로. 검토대기10/10, 사람 결정0·외부 동작0. 구형 Text-v1 부분 실패4회는 본문에 별도 명시했다.
- 구조도에서 정책 검색·설명과 버전 규칙 평가를 병렬로 표시했다. 이미지 분석은 담당자 참고 근거이며 이미지 점수를 정책 자동입력이나 결함 종류·위치 확정으로 표시하지 않았다.
- 실제 고객 정확도, 업무시간 단축률, 비용 절감률과 ROI는 측정값이 아니다. 산업적 활용은 기대와 후속 평가 기준으로 작성했다. 새 모델 실험이나 서비스 재기동을 수행하지 않았다.

## 공식 안내와 참고문헌

- [2026 추계 제출 안내](https://dcs.or.kr/homepage/custom/submit)
- [학회 논문 양식 안내](https://dcs.or.kr/board/forms/article/284050)
- [공식 대학생 HWP 양식](https://www.dcs.or.kr/homepage/boardMedia/222832)
- [제출 폼](https://dcs.or.kr/conference/fall2026/submit)
- [Generative AI at Work](https://academic.oup.com/qje/article/140/2/889/7990658)
- [Retrieval-Augmented Generation](https://papers.nips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html)
- [Guidelines for Human-AI Interaction](https://www.microsoft.com/en-us/research/publication/guidelines-for-human-ai-interaction/)
