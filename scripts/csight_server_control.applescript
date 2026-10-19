property controllerPath : "/Users/ckdlsxor/Desktop/CSight_proejct/scripts/csight_server_control.sh"

on run
    -- User interaction must not inherit the default two-minute AppleEvent deadline.
    with timeout of 3600 seconds
        my runController()
    end timeout
end run

on runController()
    activate
    set actionChoices to {"서버 켜기 (빠른 시작)", "코드 반영 후 켜기", "서버 상태 확인", "상담원 화면 열기", "서버 끄기"}
    set chosenItems to choose from list actionChoices with title "CSight 서버 제어" with prompt "원하는 작업을 선택하세요." default items {"서버 상태 확인"} OK button name "실행" cancel button name "닫기"
    if chosenItems is false then return

    set chosenAction to item 1 of chosenItems
    if chosenAction is "서버 끄기" then
        set confirmation to display dialog "GX10의 앱 전용 Q5 엔진, 공개 시연 주소, Docker Core와 정책 검색 엔진을 정지합니다. 다른 GPU 작업, DB와 업로드 파일은 보존합니다." with title "CSight 서버 끄기" buttons {"취소", "서버 끄기"} default button "서버 끄기" cancel button "취소" with icon caution
        if button returned of confirmation is not "서버 끄기" then return
    else if chosenAction is "코드 반영 후 켜기" then
        set confirmation to display dialog "이미지 재빌드와 DB 마이그레이션을 실행합니다. 몇 분 걸릴 수 있습니다." with title "CSight 업데이트 시작" buttons {"취소", "계속"} default button "계속" cancel button "취소" with icon caution
        if button returned of confirmation is not "계속" then return
    end if

    if chosenAction is "서버 켜기 (빠른 시작)" then
        set actionName to "start"
        set progressMessage to "CSight Core와 GX10 Q5 내부 검증 엔진을 시작하고 있습니다."
    else if chosenAction is "코드 반영 후 켜기" then
        set actionName to "rebuild"
        set progressMessage to "최신 코드를 반영하고 있습니다."
    else if chosenAction is "서버 상태 확인" then
        set actionName to "status"
        set progressMessage to "서버 상태를 확인하고 있습니다."
    else if chosenAction is "상담원 화면 열기" then
        set actionName to "open"
        set progressMessage to "상담원 화면을 열고 있습니다."
    else
        set actionName to "stop"
        set progressMessage to "CSight 서버를 정지하고 있습니다."
    end if

    -- Notification delivery is optional and must never prevent server control.
    try
        with timeout of 3 seconds
            display notification progressMessage with title "CSight 서버 제어"
        end timeout
    end try
    try
        with timeout of 1800 seconds
            set commandOutput to do shell script "/bin/zsh " & quoted form of controllerPath & " " & actionName
        end timeout
        -- Background applets can stall in AEInteractWithUser before a dialog exists.
        activate
        display dialog commandOutput with title "CSight 서버 제어" buttons {"확인"} default button "확인" giving up after 60
    on error errorMessage number errorNumber
        activate
        display dialog "작업을 완료하지 못했습니다." & return & return & errorMessage & return & "오류 번호: " & errorNumber with title "CSight 서버 제어" buttons {"확인"} default button "확인" with icon stop giving up after 60
    end try
end runController
