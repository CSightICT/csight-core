# CSight Kaputt DINOv2 E1~E3 모델 실험 보고서

작성일: 2026-08-27  
대상: CSight(Customer Service + Sight + Insight) 상품 불량 고객서비스 의사결정 지원 PoC(Proof of Concept, 개념검증)

## 1. 결론

최종 모델 후보는 **E3 epoch 10 `best.pt`**다. Held-out test에서 AP(Average
Precision) 0.884863, AUROC(Area Under the Receiver Operating Characteristic Curve)
0.931604를 기록했다. Validation에서 먼저 고정한 고정밀 threshold `0.8984375`를
test에 적용했을 때 precision 0.954333, recall 0.508422였다.

이 결과는 결함 의심 건을 높은 정밀도로 우선 제시하는 데는 유용하지만, 결함의 약 절반을
놓치므로 정상 판정을 자동 확정하는 모델로 사용해서는 안 된다. CSight MVP에서는 모델
점수를 의사결정 보조 근거로 사용하고, 불확실하거나 고위험인 사례는 사람이 최종 판단한다.

## 2. 데이터와 평가 통제

| 항목 | 값 |
|---|---:|
| Train | 85,326장 |
| Validation | 4,874장 |
| Test | 10,067장 |
| Train 양성 / 음성 | 24,737 / 60,589장 |
| 이미지 누락 | 0장 |
| Split 간 `item_identifier` 중복 | 0건 |

- 학습 라벨: `defect` 이진 분류
- 보조 지표: `major_defect`
- 모델 선택: validation AP(any defect)
- 최종 test: 모델과 threshold를 동결한 뒤 1회 수행
- Test prediction SHA-256:
  `ad638035c31cab6df519083294fd4d7e94c1301a20b965f2e401251da86e4d48`
- 데이터·checkpoint·prediction 원본은 GitHub와 W&B(Weights & Biases)에 업로드하지 않음

## 3. 실험별 설계와 결과

| 실험 | 핵심 설계 | 학습 상태 | Validation AP | Validation AUROC | 판단 |
|---|---|---|---:|---:|---|
| E1 | RandomResizedCrop, Adam, 동일 LR | epoch 4 후 중단 | 0.306988 | 0.534647 | 학습 신호 정체 |
| E2 | Full-frame resize, AdamW, classifier 고LR, warmup | 8 epochs 완료 | 0.839467 | 0.917615 | 핵심 개선 |
| E3 | E2 best weights, batch 16, fused AdamW, 저LR stage-2 | 12 epochs 완료; epoch 10 선택 | **0.847034** | **0.922177** | 소폭 추가 개선 |

### E1: 실패 기준선

`RandomResizedCrop(scale=(0.08, 1.0))`가 작은 결함을 crop 밖으로 제거해도 양성 라벨을
유지할 수 있었다. Epoch 4 train loss 0.604028은 train 양성 비율을 상수로 예측했을 때의
이론적 Binary Cross-Entropy 약 0.602와 유사했고, AUROC도 0.534647에 그쳤다. 실행
장애나 OOM(Out Of Memory)은 없었으며, 사용자 요청에 따라 epoch 4 결과와 checkpoint를
저장한 뒤 중단했다.

### E2: 전처리·최적화 교정

전체 2048×2048 프레임을 1024×1024로 resize하고, AdamW와 5% warmup, backbone
`5e-6`/classifier `1e-4`의 분리 학습률을 적용했다. Validation AP가 E1 대비
0.532479 증가했다. 다만 전처리와 optimizer 설정을 동시에 바꿨으므로 향상분을 한 요소에만
귀속할 수 없다.

### E3: VRAM 활용 stage-2 학습

RTX 4090에서 batch 8/16/20을 실측했다. Batch 20은 처리량이 batch 16보다 약 6%
높았지만 장시간 실행 여유가 3GiB 미만이어서 batch 16을 선택했다. E2 best 가중치만
승계하고 optimizer/scheduler는 재시작했다. Backbone LR `2e-6`, classifier LR
`3e-5`, 2% warmup, fused AdamW로 12 epochs를 완료했다.

E3의 최고 AP는 epoch 10의 0.847034였다. Epoch 12까지 train loss는 0.246044로
감소했지만 validation loss는 0.346609로 상승하고 AP는 정체했다. E2 대비 E3의 AP
개선은 0.007567, AUROC 개선은 0.004562로 작다. 반면 major-defect AP는 E2
0.581775에서 E3 0.538402로 낮아졌다.

## 4. 최종 모델 평가

### 순위 기반 test 지표

| 지표 | 결과 |
|---|---:|
| AP(any defect) | 0.884863 |
| AP(major defect) | 0.571935 |
| AUROC | 0.931604 |
| Recall@50% precision | 0.975047 |
| Recall@1% FPR | 0.486588 |

### Validation 동결 threshold의 test 결과

| 항목 | 결과 |
|---|---:|
| Threshold | 0.8984375 |
| TP / FP / TN / FN | 1,630 / 78 / 6,783 / 1,576 |
| Precision | 0.954333 |
| Recall | 0.508422 |
| Specificity | 0.988631 |
| F1 | 0.663411 |

Threshold는 validation 목표 precision 0.90을 기준으로 선택했다. Validation에서
precision 0.900126, recall 0.518572였고 test에서 precision은 더 높았지만 recall은
비슷했다. 따라서 PoC 라우팅은 다음처럼 제한한다.

- 점수 ≥ 0.8984375: `결함 고신뢰 후보`로 상담원에게 우선 제시
- 점수 < 0.8984375: `정상`으로 확정하지 않고 사람 검토 또는 추가 증거 요청
- 고액·안전·분쟁 조건: 점수와 무관하게 사람 또는 전문 담당자에게 이관

## 5. 해석과 한계

- E2가 성능 향상의 대부분을 만들었고 E3 추가 학습의 한계효용은 작았다.
- 현재 모델은 이진 any-defect 분류기이며 결함 유형·위치·마스크를 직접 출력하지 않는다.
- Kaputt test 성능은 실제 한국어 고객문의·촬영환경·상품 분포의 성능을 보장하지 않는다.
- 단일 seed 결과이므로 통계적 변동 폭을 측정하지 않았다.
- 공개 논문의 ViT-S 결과와는 학습 epoch, 코드, 전처리, 모델 선택 규칙이 달라 직접적인
  우열 비교가 어렵다. 논문 수치는 방향성 참고로만 사용한다.

## 6. 재현 정보

- 모델: `facebook/dinov2-small` 기반 DINOv2 ViT-S/14
- E1 W&B run: `93fdt5a0`
- E2 W&B run: `0kitqdog`
- [E3 W&B run](https://wandb.ai/kimhrin-sun-moon-university/csight-kaputt-dinov2/runs/e33m1xdx)
- [Kaputt 공식 배포 페이지](https://huggingface.co/datasets/amazon/kaputt)
- [Kaputt 원 논문](https://cdn.amazon.science/d8/db/7b9051f6462298230e78b0f856b1/8342-kaputt-final.pdf)

## 7. 다음 모델 작업

1. E3 checkpoint, preprocess, threshold, label 정의를 하나의 버전으로 패키징한다.
2. 같은 입력에 같은 확률을 반환하는 Vision API contract test를 만든다.
3. 실제 PoC 상품 1종을 촬영해 Kaputt와의 domain shift를 확인한다.
4. 결함 유형·위치가 필요하면 VLM(Vision-Language Model, 시각언어모델) 또는 별도
   multi-label/detection head를 추가하고 이진 분류 점수와 역할을 분리한다.


