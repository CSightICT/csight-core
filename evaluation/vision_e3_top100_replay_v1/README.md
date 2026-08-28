# E3 Top-100 selected-positive replay v1

## 목적

비전 담당자가 전달한 Kaputt held-out test의 `E3 정답 확신 상위 100장`을 실제 E3 HTTP와
CSight Core의 Case → Evidence → Analysis 경로로 재생한다. 원본은 Git이나 Web 정적 자산으로
복사하지 않고 전달 폴더에서 읽으며, 결과는 Git에서 제외된 `local-data/`에 저장한다.

이 평가는 **모델 성능 평가가 아니라 성공 사례 연결 재현 검사**다. 입력은 결함 100장,
정상 0장이며 E3가 이미 0.5 기준으로 맞힌 사례만 사전 선택됐다. 따라서 accuracy, recall,
specificity, FPR, calibration, 제품 적합성 또는 Limited PoC 승격 근거로 사용할 수 없다.

## 검증 범위

- README·CSV·JSON·JPEG 100장의 파일 구조, 순위, UUID, SHA-256, decode, 크기, EXIF/ICC 부재
- source summary와 실제 파일·manifest 집계의 일치
- exact E3 model/version/revision과 동결 threshold `0.8984375`
- 실제 E3 100장 순차 forward와 0.5 source selection 기준 replay hit
- Detection 0인 image-level `ANY_DEFECT` 경계
- 육안 검토한 경질 플라스틱 6장의 local Core 저장·Worker·조회 재현
- 직접 E3 score와 Core에 append-only 저장된 score의 일치

`defect_types`는 source annotation일 뿐 E3 예측으로 변환하지 않는다. Threshold 미만은
`정상`이 아니라 `고신뢰 결함 후보 기준 미만`이다. Human Decision이나 External Action은
이 평가가 자동 생성하지 않는다.

## 고정 Core 표본

rank 003, 032, 054, 058, 078, 080을 내부 연결용으로만 사용한다. 모두 manifest상
`plastic_hard`와 `major_defect=True`이며 서로 다른 item이다. rank 061은 개인 이름이 보여
제외했다. 이 표본을 기존 HDP-100의 다섯 Human Gold 시나리오 대표 이미지라고 부르지 않는다.

## 실행

먼저 실제 E3와 Core를 준비한다.

```bash
make health-vision-e3
make up-e3-scenario-poc
```

그다음 전달 폴더를 명시해 실행한다.

```bash
make replay-e3-top100 \
  E3_TOP100_PACKAGE=/absolute/path/to/top100_e3_correct_test_images_2026-08-28
```

기본 출력은 다음과 같다.

```text
local-data/e3-top100-replay/replay_report.json
```

보고서에는 원본 경로와 이미지 bytes를 넣지 않는다. 전체 package content-tree SHA, 입력별
SHA·score·latency, 분자·분모, Core opaque ID, report 자체 SHA와 제한 문구만 남긴다.

## 사용 제한

전달 패키지에는 license, 원소유자, dataset revision, annotation provenance, 공개 재배포 권리가
없다. 브랜드·라벨·바코드도 보일 수 있으므로 권리 확인 전에는 내부 비상업 연구 PoC에만 쓰고,
현재 공개 Web 도메인에 원본·thumbnail·signed URL을 게시하지 않는다.
