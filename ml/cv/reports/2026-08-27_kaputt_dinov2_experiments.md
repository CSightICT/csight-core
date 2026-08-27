# Kaputt DINOv2 결함 분류 실험 기록

## 1. 문서 목적

이 문서는 CSight(Customer Service + Sight + Insight)의 시각 결함 분석
PoC(Proof of Concept, 개념검증)를 위해 수행한 Kaputt DINOv2 ViT-S/14 기준
실험과 후속 실험 설계를 기록한다. 모델 출력은 고객 서비스 의사결정의 보조 근거이며,
불확실하거나 위험도가 높은 사례의 최종 결정은 사람이 수행한다.

작성 시각은 2026-08-27(Asia/Seoul)이다. 아래 수치는 실제 원격 RTX 4090 실행과
W&B(Weights & Biases) 기록에서 확인한 값만 기재한다.

## 2. 공통 데이터와 평가 원칙

| 항목 | 값 |
|---|---:|
| Train | 85,326장 |
| Validation | 4,874장 |
| Test | 10,067장 |
| Train 결함 양성 | 24,737장(28.99%) |
| Train 결함 음성 | 60,589장(71.01%) |
| 누락 이미지 | 0장 |
| Split 간 item identifier 중복 | 0건 |

- 학습 대상은 `defect` 이진 라벨이다.
- `major_defect`는 보조 평가 지표로만 사용한다.
- 모델 선택은 validation의 AP(Average Precision)를 기준으로 한다.
- test split은 모델과 임계값을 고정한 뒤 한 번만 평가한다.
- Kaputt 이미지와 checkpoint는 워크스테이션에만 저장하며 W&B나 GitHub에
  업로드하지 않는다.

## 3. 실험 E1 — RandomResizedCrop 기준선

### 3.1 실행 설정

| 항목 | 값 |
|---|---|
| W&B run ID | `93fdt5a0` |
| 모델 | `facebook/dinov2-small` |
| 학습 모드 | 전체 파인튜닝 |
| 입력 해상도 | 1024×1024 |
| Batch size | 8 |
| Optimizer | Adam |
| Backbone·classifier LR | 모두 `5e-6` |
| Weight decay | 0.05, 전체 trainable parameter에 적용 |
| Scheduler | warmup 없는 cosine decay |
| Precision | BF16 |
| Gradient checkpointing | 사용 |
| Seed | 42 |
| 계획 epoch | 8 |

### 3.2 실제 전처리

설정상 flip과 RandAugment만 의도했으나, `timm.create_transform`의 학습 기본값으로
다음 변환이 삽입됐다.

```text
RandomResizedCrop(size=1024, scale=(0.08, 1.0), ratio=(0.75, 1.3333))
RandomHorizontalFlip(p=0.5)
RandomVerticalFlip(p=0.5)
RandAugment(magnitude=9, num_layers=2, magnitude_std=0.5)
Normalize(ImageNet mean/std)
```

원본 표본 200장의 크기는 모두 2048×2048이었다. RandomResizedCrop은 원본 면적의
8%만 선택할 수 있으므로 작은 결함이 crop 밖으로 제거되어도 원래 결함 라벨이 유지되는
학습 신호 오염 가능성이 있다.

### 3.3 완료 epoch 결과

<!-- E1_FINAL_METRICS_START -->
| Epoch | Train loss | Validation loss | AP(any defect) | AP(major defect) | AUROC | Recall@50% precision | Recall@1% FPR |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.608741 | 0.594152 | 0.302316 | 0.098885 | 0.530820 | 0.002913 | 0.008012 |
| 2 | 0.605995 | 0.601750 | 0.301540 | 0.097748 | 0.533832 | 0.000000 | 0.007283 |
| 3 | 0.604709 | 0.610354 | 0.302445 | 0.094835 | 0.534173 | 0.000728 | 0.008012 |
| 4 | 0.604028 | 0.599246 | **0.306988** | 0.092444 | **0.534647** | 0.000728 | **0.012382** |
<!-- E1_FINAL_METRICS_END -->

E1은 사용자의 요청에 따라 진행 중이던 epoch 4의 validation과 checkpoint 저장을
완료한 뒤 PID `1345398`에 종료 신호를 보내 중단했다. W&B run ID와 원격
`best.pt`·`last.pt`는 비교 기준으로 보존한다.

### 3.4 관찰과 해석

- Train loss는 감소했지만 감소 폭은 epoch 1 대비 epoch 4에서 약 0.0047이다.
- Train 양성 비율 28.99%를 항상 예측하는 상수 모델의 이론적 BCE는 약 0.602다.
  Epoch 4 train loss 0.6040은 이 기준과 매우 가깝다.
- Validation 양성 비율은 약 28.17%이므로 무작위 순위의 기대 AP는 약 0.2817이다.
  관측 최고 AP 0.3070은 이를 소폭 상회하지만 강한 판별 성능으로 보기 어렵다.
- AUROC 0.5346과 매우 낮은 Recall@50% precision은 현재 checkpoint를 실제 CS
  자동 판단에 사용할 근거가 부족함을 뜻한다.
- 실행 프로세스, GPU, W&B 동기화, checkpoint 저장은 정상이며 OOM, NaN,
  traceback은 확인되지 않았다.

### 3.5 코드 진단

우선순위가 높은 원인은 다음과 같다.

1. `RandomResizedCrop(scale=(0.08, 1.0))`이 작은 결함을 제거할 수 있다.
2. 무작위 초기화된 classifier와 pretrained backbone에 동일한 `5e-6`을 적용했다.
3. `Adam(weight_decay=0.05)`이 bias와 LayerNorm을 포함한 모든 파라미터에 적용됐다.
4. warmup 없이 8 epoch cosine decay를 적용해 classifier가 적응하기 전에 LR이 감소한다.
5. `early_stopping_patience=2`는 작은 AP 변동에 비해 공격적이다.

## 4. 실험 E2 — Full-frame resize + optimizer v2

### 4.1 실험 가설

전체 2048×2048 프레임을 결함 영역 손실 없이 1024×1024로 resize하고, 무작위
초기화 classifier에 더 높은 학습률을 적용하면 기준선보다 빠르게 판별 신호를 학습할
것으로 예상한다. 이는 검증할 가설이며 성능 향상을 사전에 확정하지 않는다.

### 4.2 변경 사항

| 영역 | E1 | E2 |
|---|---|---|
| 공간 변환 | RandomResizedCrop 8~100% | 전체 frame을 1024×1024로 resize |
| Flip | 코드에 0.5 하드코딩 | YAML 값을 실제 적용 |
| Optimizer | Adam | AdamW |
| Backbone LR | `5e-6` | `5e-6` |
| Classifier LR | `5e-6` | `1e-4` |
| Weight decay | 전체 파라미터 0.05 | matrix weight 0.05, bias·LayerNorm 0 |
| Warmup | 없음 | 총 update의 5% |
| Early stopping patience | 2 | 3 |
| Gradient checkpointing | 사용 | 미사용, 스모크에서 VRAM 검증 후 확정 |
| BCE | 일반 BCE | 동일한 일반 BCE |

양성 가중 BCE는 E1과의 손실 비교 가능성을 유지하기 위해 E2에는 적용하지 않는다.

### 4.3 검증 절차

1. Ruff, format, pytest, compileall을 통과한다.
2. 생성된 train transform의 첫 연산이 전체-frame `Resize`인지 확인한다.
3. `RandomResizedCrop`이 포함되지 않았는지 확인한다.
4. 1024px, batch 8, BF16으로 짧은 스모크 backward를 수행한다.
5. OOM이 없으면 전체 train/validation 학습을 W&B online 모드로 시작한다.
6. E1과 epoch별 train loss, validation AP, AUROC를 비교한다.
7. E2의 모델·임계값을 확정하기 전에는 test split을 사용하지 않는다.

실제 사전 검증 결과:

- Ruff check/format: 통과
- pytest: 4건 통과
- Python compileall: 통과
- Full-frame transform: 첫 연산 `Resize`, `RandomResizedCrop` 미포함 확인
- 256 train / 128 validation full-finetune smoke: 완료, OOM 없음
- 1024px batch 8 단일 backward: 0.390초, CUDA peak allocation 약 8,902MiB

스모크 지표는 작은 선두 표본에 대한 파이프라인 검증값이므로 성능 근거로 사용하지
않는다.

### 4.4 성공 판단

- 1차: epoch 1~3의 train loss 감소 폭이 E1보다 명확히 커야 한다.
- 2차: validation AP가 E1 최고값을 재현성 있게 상회해야 한다.
- 안전성: NaN·OOM 없이 best/last checkpoint가 저장되어야 한다.
- 제품 관점: 고정 정밀도에서 결함 recall이 개선되는지 별도로 확인한다.

### 4.5 정식 실행 상태

| 항목 | 값 |
|---|---|
| 시작 시각 | 2026-08-27 03:41 KST |
| W&B run ID | `0kitqdog` |
| 원격 PID | `1616891` |
| 초기 GPU utilization | 100% |
| 초기 GPU memory | 약 10,141 / 24,564MiB |
| 초기 로그 오류 | 없음 |

Warmup 동작도 확인했다. Global step 260에서 backbone LR은 약 `3.06e-7`,
classifier LR은 약 `6.12e-6`으로 기록됐으며, 두 값은 각각 목표 LR `5e-6`과
`1e-4`를 총 update의 5% 동안 선형 증가시키는 설정과 일치한다.

### 4.6 최종 실행 결과

E2는 2026-08-27 09:16 KST에 8 epoch, 85,328 optimizer step을 모두 완료했다.
총 소요 시간은 약 5시간 35분이며 W&B 상태는 `finished`다. 로그에서 OOM, NaN,
CUDA error, traceback은 확인되지 않았다.

| Epoch | Train loss | Validation loss | AP(any defect) | AP(major defect) | AUROC | Recall@50% precision | Recall@1% FPR |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.554498 | 0.452370 | 0.660360 | 0.451215 | 0.819970 | 0.806264 | 0.147123 |
| 2 | 0.485310 | 0.418983 | 0.736667 | 0.477760 | 0.885753 | 0.855790 | 0.238165 |
| 3 | 0.443242 | 0.392075 | 0.756533 | 0.405262 | 0.887083 | 0.878369 | 0.236708 |
| 4 | 0.412847 | 0.368268 | 0.792880 | 0.532142 | 0.889075 | 0.904588 | 0.286235 |
| 5 | 0.379501 | 0.344199 | 0.815662 | 0.543146 | 0.903650 | 0.925710 | 0.319738 |
| 6 | 0.353069 | 0.326788 | 0.831477 | **0.595151** | 0.912255 | **0.942462** | **0.372178** |
| 7 | 0.330804 | 0.321214 | 0.837311 | 0.568850 | 0.911662 | 0.939548 | 0.352513 |
| 8 | **0.317008** | **0.320136** | **0.839467** | 0.581775 | **0.917615** | 0.938820 | 0.355426 |

AP(any defect)를 모델 선택 기준으로 사용했으므로 epoch 8 checkpoint가 `best.pt`다.
`best.pt`와 `last.pt`는 각각 약 253MiB이며 원격 워크스테이션에 보존됐다.

### 4.7 E1 대비 비교

| 지표 | E1 최고/최종 보존값 | E2 최종값 | 절대 변화 |
|---|---:|---:|---:|
| Train loss | 0.604028 | 0.317008 | -0.287020 |
| Validation loss | 0.599246 | 0.320136 | -0.279110 |
| AP(any defect) | 0.306988 | 0.839467 | +0.532479 |
| AUROC | 0.534647 | 0.917615 | +0.382968 |
| Recall@50% precision | 0.000728 | 0.938820 | +0.938092 |
| Recall@1% FPR | 0.012382 | 0.355426 | +0.343044 |

E2에서는 train loss와 validation loss가 epoch 전반에 걸쳐 함께 감소했고,
AP(any defect)는 8개 epoch 동안 매번 최고값을 갱신했다. E1의 정체 현상이 해소됐다는
근거는 충분하다. 다만 E2는 전처리, optimizer, classifier LR, warmup을 함께 변경했으므로
향상분을 단일 변경 요소에만 귀속할 수 없다.

AP(major defect)는 epoch 6에서 0.595151로 최고였고 epoch 8에서는 0.581775로
하락했다. 현재 모델 선택 기준은 any-defect AP이므로 epoch 8을 선택했지만, major defect
탐지를 별도 제품 목표로 삼는다면 multi-objective checkpoint 정책을 추가로 검토해야 한다.

## 5. 현재 결론과 다음 단계

E1은 파이프라인 기준선으로는 유효하지만 모델 성능 기준선으로는 약했다. 전체-frame
resize와 optimizer v2를 적용한 E2는 validation AP 0.839467과 AUROC 0.917615를
기록하며 E1보다 명확히 개선됐다. 이는 validation 결과이며 아직 test 성능이나 실제 고객
환경 성능을 의미하지 않는다.

다음 단계는 다음 순서로 제한한다.

1. E2 `best.pt`와 설정을 동결하고 모델 선택 근거를 확정한다.
2. validation prediction으로 CSight 의사결정 지원용 후보 임계값과 불확실 구간을 정한다.
3. 모델과 임계값을 모두 고정한 뒤 test split을 한 번만 평가한다.
4. 오류 사례를 결함 유형·재질별로 분석하고, 불확실하거나 고위험인 경우 사람에게
   이관하는 규칙을 문서화한다.

