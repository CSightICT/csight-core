# doongdoong.org 영상 첫 화면

2026-09-29 기준 `https://doongdoong.org/`와 `https://doongdoong.org/login`은 이 폴더의
`index.html`을 보여주고 `/video.mp4`로 무음 시연 영상을 재생한다. `www`도 동일하며
`/login/`을 지원한다. 브라우저가 허용하는 경우 음소거 상태로 자동 재생하고 재생 컨트롤을
표시한다. 공개 `/login`의 기존 CSight 로그인 화면은 영상으로 대체된다. CSight Web은
로컬 `http://127.0.0.1:8080/login`에서 그대로 접근할 수 있다. `/api`, `/auth`,
`/web-health` 등 나머지 공개 경로는 기존 Web 서버로 간다.

Cloudflare Tunnel의 첫 화면, `/login`, 영상 파일 경로를 `127.0.0.1:8098`로 분기한다. 해당 서버는
macOS LaunchAgent `com.csight.demo-video`가 실행한다. macOS가 Desktop 경로에 대한
LaunchAgent 접근을 제한하므로 배포본은
`~/Library/Application Support/CSightVideo/`에 복사했다. 원본 파일은
`/Users/ckdlsxor/Downloads/final_v2_highres.mp4`이며 SHA-256은
`bd90b7c5420e03953457caa9792ca74920752ea9734e1f6f0972a1cb4288b998`이다.

## CSight 로그인 경로

2026-09-29 기준 기존 CSight 로그인 폼은
[`https://doongdoong.org/login2`](https://doongdoong.org/login2)에서 사용할 수 있다.
프런트 라우터는 `/login2`를 로그인 화면으로 인식하고 인증되지 않은 업무 경로도
`/login2`로 이동시킨다. `/login`은 영상으로 유지한다. `www`의 `/login2`도 같은 Web에
연결된다. 공개 `/auth/capabilities`는 현재 기존 비밀번호 로그인을 허용한다고 응답했다.

운영 Web 이미지의 이전 버전은 `csight-web:before-login2-20260929`로 보존했고, 현재
`csight-web:dev`와 `csight-web:login2-20260929`는 `/login2`가 포함된 동일 이미지다.
기존 운영 번들을 기준으로 `scripts/patch_deployed_login2_bundle.py`와
`scripts/login2-overlay.Dockerfile`로 이번 라우트 변경만 이미지에 반영했다. 다음 전체
Web 빌드에도 경로가 남도록 `web/src/App.tsx`와 회귀 테스트를 갱신했다. 실제 계정으로
로그인 완료 후 업무 화면까지 도달하는 검사는 계정 자격 증명을 사용하지 않아 실행하지 않았다.

## 확인

```sh
launchctl print gui/$(id -u)/com.csight.demo-video
/opt/homebrew/bin/cloudflared tunnel --config ~/.cloudflared/config.yml ingress validate
curl -I https://doongdoong.org/
curl -I -H 'Range: bytes=0-1023' https://doongdoong.org/video.mp4
curl -I https://doongdoong.org/login
curl -I https://doongdoong.org/login2
curl -I http://127.0.0.1:8080/login
```

Tunnel 설정은 변경 전 `~/.cloudflared/config.yml.backup-before-video-20260928-192609`에
보관했다. 원복 시 해당 백업을 `config.yml`에 복사하고 Tunnel LaunchAgent만 재시작한다.
`/login` 추가 직전 설정은
`~/.cloudflared/config.yml.backup-before-login-video-20260929-201440`에 보관했다.
`/login`만 이전 CSight 화면으로 되돌릴 때는 이 두 번째 백업을 사용한다.
영상 서버는 필요 시 `launchctl bootout gui/$(id -u)/com.csight.demo-video`로 중단한다.
Mac 또는 Tunnel이 꺼져 있으면 공개 링크도 동작하지 않는다.
