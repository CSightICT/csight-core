# Evidence 이미지 보안 격리 자격 검증

## 목적과 안전 경계

이 검증은 실제 고객 이미지를 받기 전에 Evidence 업로드가 저장 전에 정화되고 악성 파일 검사기
장애 시 실패-폐쇄하는지 실제 HTTP 경로로 확인한다. 현재 시연 서버와 분리된 Docker Compose
프로젝트 `csight-evidence-qualification`과 임시 PostgreSQL, RabbitMQ, MinIO, ClamAV를 사용하며,
종료 시 컨테이너·네트워크·볼륨을 제거한다. 운영 DB와 운영 MinIO volume은 사용하지 않는다.

ClamAV 이미지는 `clamav/clamav:1.5.4`의 정확한 digest로 고정한다. 검증 스택은
`linux/amd64`로 실행되므로 Apple Silicon에서의 통과는 구성과 HTTP 계약의 증거이며, RTX 4090
x86_64 파일럿 호스트에서 같은 명령을 다시 통과하기 전에는 해당 호스트 자격으로 전용하지 않는다.

## 실행

Docker가 실행 중인 저장소 루트에서 다음을 실행한다.

```sh
make qualify-evidence-security
```

스크립트는 무작위 격리 자격 증명을 메모리와 프로세스 환경에만 만들고 최신 migration을 적용한 뒤
다음 관문을 실제 API 업로드와 readback으로 검사한다.

- EXIF orientation이 적용되고 private EXIF와 원본 marker가 없는 JPEG/PNG/WebP 재인코딩본만 저장
- EICAR 입력은 decode·저장 전에 HTTP 422 `UNSAFE_EVIDENCE`로 거부
- 손상된 이미지 본문은 HTTP 422 `INVALID_IMAGE_CONTENT`로 거부
- 요청 상한을 넘는 multipart 본문은 HTTP 413으로 거부
- ClamAV를 중단한 뒤 정상 이미지도 HTTP 503 `EVIDENCE_SECURITY_UNAVAILABLE`로 거부

정상 검사와 scanner-outage 검사 모두 `verdict: PASS`이고 프로세스 exit code가 0이어야 한다.
실패를 우회하기 위해 sanitizer 또는 malware scanner를 끄거나, 원본을 먼저 저장하는 fallback을
추가하지 않는다.

PII와 Secret이 없는 두 결과는 mode `0600`의
`local-data/evidence-security-qualification/latest/healthy-report.json`과
`outage-report.json`에 저장한다. 상위 디렉터리는 mode `0700`이며 파일 수정 시각보다 오래된 결과를
현재 자격으로 재사용하지 않는다.

## 2026-08-30 격리 실측 결과

Apple Silicon 개발 Mac의 Docker에서 고정된 amd64 ClamAV 이미지를 사용한 결과 두 단계 모두
`PASS`였다.

- 정상 JPEG 저장과 readback: PASS
- orientation 적용, EXIF 제거, 원본 bytes 재인코딩: PASS
- EICAR·손상 이미지·과대 요청 차단: PASS
- ClamAV 중단 시 실패-폐쇄: PASS
- 종료 후 `csight-evidence-qualification` 컨테이너·볼륨 잔존: 0
- 기존 시연 서버 영향: Core 9개, API, 상담원 화면, 정책 검색, 공개 시연 주소 정상

## 파일럿 호스트 활성화 조건

1. 파일럿용 x86_64 호스트에서 이 자격 검증을 그대로 다시 실행한다.
2. Production 설정에서 Pillow 정화와 ClamAV scanner를 둘 다 필수로 켠다.
3. ClamAV signature 갱신 실패, health 실패, timeout을 업로드 허용으로 낮추지 않는다.
4. Reverse proxy에도 요청 크기와 동시 업로드 제한을 설정한다.
5. 실패 응답과 구조화 로그에 파일 본문, 파일명, object key, 고객 식별정보를 남기지 않는다.
6. 실제 고객 데이터를 넣기 전에 tenant RLS, 고객 IdP 운영 연결, 명시적 retention, off-host 복원,
   경보 전달 관문을 별도로 통과한다.

이 검증은 이미지 반입 경로 하나의 자격일 뿐이며 실제 고객 파일럿 승인, 개인정보 전체 수명주기,
백업 복원 또는 모델 품질을 증명하지 않는다. 모델 결과는 계속 참고 권고이고 실제 환불·메일·결제
동작을 수행하지 않는다.
