# Kaputt 기반 비전 모델 최종 권장 구조

## 결론

**Kaputt만 사용한다면 가장 좋은 구조는 2단계 YOLO가 아니라, `고해상도 Global–Local 멀티태스크 ViT` 구조입니다.**

```text
Kaputt Query Image
        │
        ├──────── 전체 Tray 이미지 1024×1024 ────────┐
        │                                            │
        └─ 제공된 Item Mask → 상품 Crop 1024×1024 ──┤
                                                     ▼
                                         Shared DINOv3/DINOv2 ViT
                                                     │
                          ┌──────────────────────────┴─────────────────────────┐
                          │                                                    │
                 Global Feature                                      Local Patch Feature
          전체 문맥·누출·구성품·포장 상태                       미세 균열·눌림·표면 손상
                          │                                                    │
                          └──────── Gated Fusion + Patch-MIL ──────────────────┘
                                                     │
             ┌──────────────────┬────────────────────┼────────────────┬────────────────┐
             ▼                  ▼                    ▼                ▼                ▼
       하자 유무 Head      심각도 Head         하자 유형 Head    재질 보조 Head    의심 영역 Heatmap
        Binary             Ordinal             Multi-label         Auxiliary       Weak Localization
                                                     │
                                             Confidence Calibration
                                                     │
                                             판정 / 검토 필요 분기
                                                     │
                              Vision JSON + 고객 텍스트 → LLM + RAG
```

구조를 요약하면:

> **Mask-Guided Dual-View Multi-Task Defect Classification with Patch-MIL**

---

## 1. 왜 이 구조가 적합한가

Kaputt에는 다음 라벨이 있습니다.

- `no defect / minor / major`
- 7개 하자 유형
- 상품 재질
- 상품 segmentation mask
- 동일 상품의 reference 이미지 최대 3장

반면 **하자 자체의 bbox나 segmentation mask는 없습니다.**

따라서 하자 Detection보다 이미지 단위 Classification과 약지도학습 localization이 데이터 구조에 더 잘 맞습니다.

Kaputt 공개 실험에서도 전체 tray 이미지를 1024×1024로 입력한 DINOv2 ViT-S가 강한 성능을 보였습니다.

- AP_any: **90.67**
- AP_major: **91.45**
- AUROC: **94.27**

즉, Kaputt에서는 다음 방향이 가장 합리적입니다.

```text
Supervised high-resolution ViT
>
Reference-based anomaly detection
>
Zero-shot VLM
```

---

## 2. 입력은 Full Tray와 Item Crop을 같이 사용

### Global Branch: 전체 Tray 이미지

```text
2048×2048 원본
    ↓
1024×1024 resize
    ↓
Global ViT branch
```

전체 이미지는 다음 하자에 중요합니다.

- 상품 주변에 흘러나온 액체나 가루
- 상품에서 분리된 구성품
- 포장 전체의 개봉 상태
- 상품 주변의 오염
- 여러 구성품 사이의 관계

상품 Crop만 사용하면 `spillage`, `missing_unit` 같은 전역적인 증거를 놓칠 수 있습니다.

### Local Branch: 상품 Crop

```text
Item segmentation mask
    ↓
Bounding box 변환
    ↓
10~15% padding
    ↓
1024×1024 상품 Crop
    ↓
Local ViT branch
```

Local branch는 다음에 유리합니다.

- 작은 찢김
- 미세한 찌그러짐
- 스크래치
- 표면 오염
- 포장 모서리 손상
- 약간 열린 뚜껑

전체 이미지에서 작게 보이던 하자가 Crop 후에는 더 많은 픽셀을 차지하게 됩니다.

---

## 3. Backbone 추천

### 안정적인 기준 모델

```text
DINOv2 ViT-S/14
input: 1024×1024
```

Kaputt 공식 실험에서 직접 검증된 선택입니다.

### 최종 성능 후보

```text
DINOv3 ViT-S/16
또는
DINOv3 ViT-B/16
```

추천 실험 순서:

```text
Baseline:
DINOv2 ViT-S/14

Experiment A:
DINOv3 ViT-S/16

Experiment B:
DINOv3 ViT-B/16
```

DINOv3가 Kaputt에서 DINOv2보다 반드시 좋다는 보장은 없으므로 A/B 테스트가 필요합니다.

---

## 4. 두 Branch는 같은 ViT를 공유

처음부터 ViT 두 개를 독립적으로 두면 파라미터와 학습량이 크게 증가합니다.

권장 구조:

```text
Full Tray ─┐
           ├─ Shared DINO Encoder
Item Crop ─┘
```

두 입력에는 서로 다른 `view embedding` 또는 작은 adapter만 추가합니다.

```text
Global view token
Local view token
```

구현 예시:

```python
images = torch.cat([global_images, local_images], dim=0)
features = backbone(images)

global_features, local_features = features.chunk(2, dim=0)
```

---

## 5. CLS Token만 쓰지 말고 Patch-MIL 사용

Kaputt 하자는 이미지 전체가 아니라 작은 일부 영역에만 나타날 수 있습니다.

일반적인 ViT Classification:

```text
전체 Patch
    ↓
CLS token
    ↓
Classification
```

이 경우 작은 스크래치나 구멍의 신호가 전체 특징에 묻힐 수 있습니다.

따라서 Local branch에서는 **Patch-level Multi-Instance Learning(MIL)** 을 권장합니다.

```text
Local ViT patch tokens
    ↓
각 patch의 defect score 계산
    ↓
상위 k개 patch 또는 attention-weighted pooling
    ↓
Local defect representation
```

개념 예시:

```python
patch_scores = defect_patch_head(local_patch_tokens)
weights = torch.softmax(patch_scores, dim=1)

local_feature = torch.sum(
    weights * local_patch_tokens,
    dim=1
)
```

또는 상위 5~10% suspicious patch만 선택할 수 있습니다.

```text
Top-k suspicious patches
    ↓
Pooling
    ↓
하자 분류
```

장점:

- 하자 bbox 없이도 학습 가능
- 작은 결함 신호를 강조할 수 있음
- 어느 patch가 하자 판단에 기여했는지 heatmap 생성 가능

---

## 6. Global + Local Feature Fusion

초기에는 단순한 feature fusion이면 충분합니다.

```python
fused = torch.cat([
    global_feature,
    local_feature,
    torch.abs(global_feature - local_feature),
    global_feature * local_feature,
], dim=-1)
```

구조:

```text
[Global, Local, |Global−Local|, Global×Local]
                       ↓
                   Fusion MLP
                       ↓
                 Shared Feature
```

성능이 부족할 경우 이후 Cross-Attention을 추가할 수 있습니다.

```text
Local Patch Query
       ↓
Global Patch Key / Value
       ↓
Cross-Attention
```

처음부터 복잡하게 만들기보다는 단순 Fusion부터 검증하는 것이 좋습니다.

---

## 7. 출력 Head 구성

### 7.1 하자 유무 Head

```text
정상 / 하자 있음
```

```python
p_any = sigmoid(logit_any)
```

Loss:

```text
BCEWithLogitsLoss
또는
Focal Loss
```

---

### 7.2 심각도 Head — Ordinal Classification

Kaputt 심각도에는 순서가 있습니다.

```text
no defect < minor < major
```

따라서 일반 3-class Softmax보다 ordinal regression이 더 자연스럽습니다.

예:

```text
Head 1: minor 이상인가?
Head 2: major 이상인가?
```

출력:

```text
P(y ≥ minor)
P(y ≥ major)
```

최종 판정:

```text
둘 다 낮음       → no defect
minor만 높음     → minor
major도 높음     → major
```

CORAL 같은 ordinal regression 방식을 사용할 수 있습니다.

---

### 7.3 하자 유형 Head — Multi-label

Kaputt 하자 유형:

```text
penetration
deformation
actuation
deconstruction
spillage
superficial
missing_unit
```

하나의 이미지에 여러 하자가 동시에 존재할 수 있으므로 7-class Softmax가 아니라 7개 독립 Sigmoid를 사용해야 합니다.

```python
type_probs = torch.sigmoid(type_logits)
```

Loss:

```text
BCEWithLogitsLoss
또는
Asymmetric Loss
```

---

### 7.4 Material Head — Auxiliary

재질 정보는 최종 서비스 출력에는 필수가 아니지만 보조 학습 신호로 사용할 수 있습니다.

예:

```text
cardboard
plastic bag
hard plastic
bubble wrap
tight wrap
paper
book-paper
book-plastic
other
```

같은 변형이라도 재질에 따라 정상/불량 판단 기준이 달라질 수 있으므로 보조적인 representation learning에 도움이 될 수 있습니다.

---

## 8. 추천 Loss 구성

초기값 예시:

```text
L_total =
    1.0 × L_any
  + 0.6 × L_severity
  + 0.7 × L_defect_type
  + 0.1 × L_material
  + 0.2 × L_patch_MIL
  + 0.1 × L_consistency
```

`L_consistency`는 출력 간 모순을 줄이기 위한 항입니다.

예:

```text
any_defect = false
그런데
spillage = true
```

이런 출력에는 penalty를 줄 수 있습니다.

개념적으로:

```text
P(any defect)
≈ max(
    P(minor 이상),
    P(defect types)
)
```

Loss weight는 validation 성능을 기준으로 조정합니다.

---

## 9. 하자 위치 시각화

Kaputt에는 하자 mask가 없으므로 heatmap을 실제 segmentation 정답처럼 사용하면 안 됩니다.

```text
Local Patch Scores
        ↓
원본 해상도로 Upsampling
        ↓
하자 의심 영역 Heatmap
```

UI 표현은 다음처럼 하는 것이 적절합니다.

> 모델이 하자 판정에 사용한 주요 의심 영역

### SAM은 선택적 후처리

```text
Patch-MIL Heatmap
       ↓
고신뢰 Point / Bounding Box
       ↓
SAM
       ↓
경계가 매끄러운 의심 영역
```

다만 SAM 결과는 **pseudo-mask**이며 실제 하자 annotation이 아닙니다.

```text
SAM이 하자 여부를 판단하는 것 X
SAM이 전달받은 영역의 경계를 정리하는 것 O
```

따라서 최종 하자 probability에는 SAM을 직접 개입시키지 않는 편이 안전합니다.

---

## 10. Reference 이미지는 메인 모델에서 제외

Kaputt에는 동일 상품 reference 이미지가 최대 3장 있지만 다음 문제가 있습니다.

- 앞면/뒷면이 다를 수 있음
- 상품 각도와 방향이 다름
- 포장 디자인이 다를 수 있음
- reference 자체가 완벽한 정상 상태가 아닐 수 있음
- reference 수가 일정하지 않음

따라서 기본 모델은:

```text
Query-only Global–Local Model
```

Reference는 2차 연구 분기로 두는 것이 좋습니다.

### Reference를 넣는다면

```text
Query-only score: s_query

Reference comparison score: s_ref

Reference reliability gate:
g = sigmoid(
    pose_similarity
    + appearance_similarity
    + reference_quality
)

Final:
s_final = s_query + g × s_ref
```

Reference가 충분히 비슷하고 신뢰할 수 있을 때만 반영합니다.

특히 다음 유형의 보조 정보로 활용하는 것이 좋습니다.

```text
missing_unit
actuation
deconstruction
```

---

## 11. YOLO와 UniVAD의 위치

### YOLO

```text
상품 탐지 YOLO:
Kaputt에는 item mask가 있으므로 데이터셋 실험에서는 불필요

하자 탐지 YOLO:
하자 bbox/mask가 없으므로 기본 Kaputt 라벨만으로는 학습 불가능

YOLO Classification:
비교 Baseline으로는 가능
```

실제 고객 이미지에서 상품 Crop이 필요하다면 별도의 상품 YOLO-Seg를 사용할 수 있습니다.

```text
고객 이미지
    ↓
상품 YOLO-Seg
    ↓
상품 Crop
    ↓
Global–Local DINO 모델
```

단, Kaputt와 실제 고객 촬영 이미지 사이에는 domain shift가 존재할 가능성이 큽니다.

### UniVAD

UniVAD나 PatchCore 같은 anomaly detection은 메인 모델보다는 보조 branch가 적합합니다.

```text
DINO 모델 confidence가 낮음
        ↓
Reference-aware anomaly branch 추가 검사
        ↓
사람 검토 여부 결정
```

---

## 12. Vision 모델 최종 출력 JSON

LLM에는 자연어보다 구조화된 결과를 전달하는 것이 좋습니다.

```json
{
  "vision_status": "defect_detected",
  "is_defective": true,
  "defect_probability": 0.931,
  "severity": "major",
  "severity_probabilities": {
    "no_defect": 0.018,
    "minor": 0.106,
    "major": 0.876
  },
  "defect_types": [
    {
      "type": "deformation",
      "probability": 0.883
    },
    {
      "type": "penetration",
      "probability": 0.624
    }
  ],
  "material": "cardboard",
  "localization_method": "patch_mil",
  "localization_reliability": "weakly_supervised",
  "requires_manual_review": false
}
```

역할 분리는 다음과 같이 유지합니다.

```text
Vision:
어떤 하자로 보이는가
얼마나 심한가

Text LLM:
고객이 무엇을 요청했는가
구매일·수령일·증빙자료는 무엇인가

RAG:
해당 하자와 구매 조건에서
교환·환불·AS 정책이 무엇인가
```

LLM이 Vision 판단을 임의로 변경하는 구조는 피합니다.

---

## 13. 실제 구현 순서

### Stage 1 — 공식 Baseline 재현

```text
Full Tray 1024
→ DINOv2 ViT-S
→ any defect binary classification
```

목표:

- Kaputt 공식 baseline 수준 재현
- 데이터 로더와 split 검증
- metric pipeline 검증

### Stage 2 — Multi-task

```text
Full Tray
→ DINOv2 / DINOv3
→ any + severity + type + material
```

### Stage 3 — Global–Local

```text
Full Tray + Item Crop
→ Shared ViT
→ Feature Fusion
→ Multi-task
```

### Stage 4 — Patch-MIL

```text
Local patch tokens
→ Top-k / Attention MIL
→ 의심 영역 Heatmap
```

### Stage 5 — Calibration

```text
Temperature Scaling
Per-class Threshold
판정 불가 / 사람 검토
```

### Stage 6 — 선택적 Reference Branch

```text
낮은 confidence
또는 missing_unit 의심
        ↓
Gated Reference Comparison
```

---

# 최종 구조

```text
                   Kaputt Query Image
                           │
             ┌─────────────┴─────────────┐
             │                           │
        Full Tray                    Item Crop
         1024px                       1024px
             │                           │
             └──── Shared DINOv3 ────────┘
                           │
              Global–Local Feature Fusion
                           │
                       Patch-MIL
                           │
       ┌───────────┬───────────┬────────────┬──────────┐
       │           │           │            │          │
   Any Defect   Severity   Defect Types   Material   Heatmap
    Binary      Ordinal     Multi-label   Auxiliary  Weak Loc.
       │
   Calibration
       │
정상 / 경미 / 심각 / 사람 검토
       │
Vision JSON + 고객 텍스트
       │
LLM 구조화 + 정책·사례 RAG
```

## 최종 권장안

- **공식 Baseline:** `DINOv2 ViT-S/14 + 1024×1024 Full Tray`
- **최종 후보:** `DINOv3 ViT-S/B + Global–Local Shared Encoder`
- **하자 분류:** Multi-task
- **심각도:** Ordinal Classification
- **하자 유형:** 7-label Multi-label Classification
- **미세 하자 처리:** Patch-MIL
- **위치 설명:** Weakly-supervised Heatmap
- **SAM:** 선택적 시각화 후처리
- **Reference:** 기본 모델에서는 제외, 이후 gated auxiliary branch로 실험
- **YOLO:** 메인 하자 판정 모델로 사용하지 않음
- **UniVAD:** low-confidence 케이스용 보조 anomaly branch
- **최종 결과:** 구조화 Vision JSON → 고객 텍스트 분석 → 정책/사례 RAG
