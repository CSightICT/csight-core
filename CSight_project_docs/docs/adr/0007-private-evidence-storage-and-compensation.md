# ADR-0007: Private Evidence 저장과 최선 노력 보상 전략

- 상태: Accepted
- 일자: 2026-08-26

## Context

상품 불량 Evidence 이미지는 민감정보를 포함할 수 있으며 PostgreSQL이나 RabbitMQ에
Binary/Base64로 저장하면 DB·메시지 크기와 접근 통제가 악화된다. PostgreSQL과 MinIO는
하나의 ACID Transaction에 참여하지 않으므로 업로드 도중 한쪽만 성공하는 부분 실패도
명시적으로 다뤄야 한다.

또한 컨테이너 내부의 `minio:9000` 같은 Endpoint로 서명한 URL은 브라우저에서 접근할 수
없다. 반대로 외부 Hostname을 일반 업로드·삭제 트래픽에 사용하면 내부 저장 경계가
불필요하게 넓어진다.

## Decision

- 원본 이미지는 Private MinIO Bucket에 저장하고 DB에는 Bucket, Object Key, 정규화한
  원본 파일명, 실제 MIME, 크기, SHA-256, 폭·높이, 생성자와 상태만 저장한다.
- 서버가 생성한 UUID로 다음 Object Key를 만든다. 원본 파일명은 경로에 사용하지 않는다.

  ```text
  tenants/{tenant_id}/cases/{case_id}/evidence/{evidence_id}/original
  ```

- `MINIO_ENDPOINT`는 Core가 업로드·확인·삭제에 사용하는 내부 Endpoint다.
  `MINIO_PRESIGNED_ENDPOINT`는 클라이언트가 Signed URL로 접근할 Hostname이다. Scheme은
  각각 `MINIO_SECURE`, `MINIO_PRESIGNED_SECURE`로 설정한다.
- Bucket은 Public으로 전환하지 않는다. 접근 API는 `AVAILABLE` Evidence에 한해
  `SIGNED_URL_TTL_SECONDS`를 적용한 짧은 Presigned GET URL을 반환한다. URL은 DB에
  저장하거나 로그에 기록하지 않는다.
- Production의 Presign Hostname은 MinIO 전체 관리면을 인터넷에 노출하는 주소가 아니다.
  신뢰할 수 있는 HTTPS Reverse Proxy 또는 Gateway가 서명된 Object GET에 필요한 제한된
  경로와 Method만 MinIO Object API로 전달해야 한다. MinIO Console, Admin API, Credential,
  내부 Endpoint는 사설망에 둔다.
- 업로드는 다음 순서를 사용한다.

  1. Principal의 Tenant 범위에서 Case 존재와 업로드 권한을 확인한다.
  2. 독립 `HashingPort` Adapter가 최대 크기를 넘지 않는 한 번의 Streaming Read로 크기와
     SHA-256을 계산하고 Stream을 되감는다.
  3. `FileInspectorPort` Adapter가 파일을 Decode하고 실제 형식/MIME, 확장자, 폭·높이와
     Pixel 수를 검증한다.
  4. `PENDING` Evidence Row를 Commit한다.
  5. 내부 Endpoint로 원본 Object를 업로드한다.
  6. 저장 결과의 Bucket, Key, MIME, 크기, SHA-256을 확인한다.
  7. Evidence를 `AVAILABLE`로 Commit한다.

- Object 저장이 실패하거나 최종 DB 갱신이 실패하면 Object 삭제와 `FAILED` 전환을 각각
  최선 노력으로 수행한다. 성공 응답은 `AVAILABLE` 전환까지 완료된 경우에만 반환한다.
- 허용 형식과 한도는 `MAX_UPLOAD_BYTES`, `ALLOWED_IMAGE_MIME_TYPES`,
  `ALLOWED_IMAGE_EXTENSIONS`, `MAX_IMAGE_PIXELS`로 주입한다. Sprint 1은 JPEG, PNG,
  WebP만 지원하며 SVG는 허용하지 않는다.
- `HashingPort`와 `FileInspectorPort`는 별도 기술 독립 Port다. Composition Root가
  `BoundedSha256Hasher`를 Pillow Inspector에 주입하며 Application은 구현 Adapter를 직접
  생성하지 않는다.

## Consequences

### 장점

- 이미지 Binary와 업무 메타데이터의 저장 책임과 접근권한을 분리한다.
- 원본 파일명과 경로 조작 문자열이 Object Key에 영향을 주지 않는다.
- DB가 `AVAILABLE`이라고 표시하기 전에 Object 저장을 확인한다.
- 내부 저장 Endpoint와 클라이언트 접근 Hostname을 배포 환경별로 분리할 수 있다.

### 비용과 제한

- 보상은 분산 Transaction이 아니며 완전한 원자성을 보장하지 않는다. 프로세스 강제 종료,
  MinIO 삭제 실패, DB 장애가 겹치면 `PENDING`/`FAILED` Row 또는 고아 Object가 남을 수
  있다.
- Sprint 1에는 주기적 Reconciliation/Orphan Cleanup Job이 없다. 운영 전 이 상태를
  탐지·복구하는 작업이 필요하다.
- Evidence 업로드용 Idempotency Key는 지원하지 않아 동일 이미지를 반복 제출하면 별도
  Evidence가 생성될 수 있다.
- EXIF 제거, 이미지 재인코딩, 개인정보 마스킹, 파생본 생성, Virus Scan은 수행하지 않는다.
  원본 EXIF와 보관·삭제 정책은 후속 보안 결정이 필요하다.

## Guardrails

- 다른 Tenant의 Case·Evidence에는 Signed URL을 발급하지 않는다.
- Case 목록이나 Evidence 메타데이터 응답에 Signed URL을 자동 포함하지 않는다.
- MinIO Access Key, Secret, 전체 Signed URL, 이미지 Binary를 로그에 기록하지 않는다.
- `PENDING`, `AVAILABLE`, `FAILED`의 전환과 보상 경로를 Integration Test로 검증한다.
