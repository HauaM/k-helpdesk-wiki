# MCP 서버 설정 가이드

KHW을 Claude Desktop 및 Claude 웹에서 사용하기 위한 MCP(Model Context Protocol) 서버 설정 방법입니다.

## 📋 개요

MCP 서버를 통해 Claude가 KHW의 기능을 직접 호출할 수 있습니다:
- 상담 내역 생성 및 검색
- 메뉴얼 자동 생성
- 메뉴얼 검색 및 검토 워크플로우

## 🚀 설치 방법

### 1. 의존성 설치

```bash
# Poetry 사용 시
poetry install

# 또는 pip 사용 시
pip install mcp
```

### 2. MCP 서버 실행 테스트

```bash
# 프로젝트 루트에서 실행
python mcp_server.py
```

정상 실행되면 MCP 서버가 stdio를 통해 대기 중입니다.

## 🔧 Claude Desktop 설정

### macOS/Linux

1. Claude Desktop 설정 파일 위치:
   ```
   ~/Library/Application Support/Claude/claude_desktop_config.json  # macOS
   ~/.config/Claude/claude_desktop_config.json                      # Linux
   ```

2. 설정 파일 편집:
   ```json
   {
     "mcpServers": {
       "khw": {
         "command": "python",
         "args": [
           "/home/hauam/workspace/k-helpdesk-wiki/mcp_server.py"
         ],
         "env": {
           "PYTHONPATH": "/home/hauam/workspace/k-helpdesk-wiki"
         }
       }
     }
   }
   ```

3. **중요**: 절대 경로를 본인의 프로젝트 경로로 수정하세요!

### Windows

1. 설정 파일 위치:
   ```
   %APPDATA%\Claude\claude_desktop_config.json
   ```

2. 설정 파일 편집 (Python 경로 주의):
   ```json
   {
     "mcpServers": {
       "khw": {
         "command": "python",
         "args": [
           "C:\\Users\\YourName\\workspace\\k-helpdesk-wiki\\mcp_server.py"
         ],
         "env": {
           "PYTHONPATH": "C:\\Users\\YourName\\workspace\\k-helpdesk-wiki"
         }
       }
     }
   }
   ```

### Poetry 가상환경 사용 시

Poetry를 사용하는 경우, Python 인터프리터 경로를 명시해야 합니다:

```bash
# 가상환경 Python 경로 확인
poetry env info --path
```

설정 파일 예시:
```json
{
  "mcpServers": {
    "khw": {
      "command": "/home/hauam/.cache/pypoetry/virtualenvs/k-helpdesk-wiki-xxxxx/bin/python",
      "args": [
        "/home/hauam/workspace/k-helpdesk-wiki/mcp_server.py"
      ]
    }
  }
}
```

## ✅ 설정 확인

1. Claude Desktop 재시작

2. Claude Desktop을 열고 새 대화 시작

3. 다음 명령어로 MCP 서버 연결 확인:
   ```
   MCP 서버 목록을 보여주세요
   ```

4. KHW 도구가 표시되면 성공! 🎉

## 🛠️ 사용 가능한 MCP Tools

### 1. create_consultation
```
새 상담 내역을 생성해주세요:
- 요약: "고객이 카드 결제 오류 문의"
- 문의내용: "카드 결제 시 에러코드 E401 발생"
- 조치내용: "카드 재등록 안내"
- 영업점: "B001"
- 직원ID: "EMP123"
```

### 2. search_consultations
```
"카드 결제 오류"와 유사한 상담 내역을 검색해주세요
```

### 3. generate_manual_draft
```
상담 ID xxx를 기반으로 메뉴얼 초안을 생성해주세요
```

### 4. search_manuals
```
"카드 결제"와 관련된 메뉴얼을 검색해주세요
```

### 5. list_review_tasks
```
승인 대기 중인 메뉴얼 검토 태스크를 보여주세요
```

### 6. approve_review_task
```
검토 태스크 ID xxx를 승인해주세요
```

### 7. reject_review_task
```
검토 태스크 ID xxx를 "중복 내용"이라는 이유로 반려해주세요
```

## 🐛 문제 해결

### MCP 서버가 연결되지 않는 경우

1. **경로 확인**
   ```bash
   # 프로젝트 경로 확인
   pwd
   # Python 경로 확인
   which python
   ```

2. **수동 실행 테스트**
   ```bash
   python mcp_server.py
   ```
   에러 메시지 확인

3. **로그 확인**
   - Claude Desktop 개발자 도구 열기 (Cmd/Ctrl + Shift + I)
   - Console 탭에서 MCP 관련 에러 확인

4. **환경변수 설정**
   `.env` 파일이 프로젝트 루트에 있는지 확인

### "not_implemented" 응답이 오는 경우

현재 MCP 서버는 구조만 만들어진 상태입니다. 실제 비즈니스 로직은 `app/services/` 레이어 구현 후 동작합니다.

TODO로 표시된 부분:
- `app/mcp/tools.py` - 각 tool의 실제 구현
- `app/services/consultation.py` - 상담 서비스 로직
- `app/services/manual.py` - 메뉴얼 서비스 로직

## 📝 개발 현황

### ✅ 완료
- [x] MCP 서버 기본 구조
- [x] 7개 Tool 정의 및 스켈레톤 구현
- [x] Claude Desktop 설정 가이드

### 🚧 TODO
- [ ] Service Layer 실제 구현
- [ ] DB 연결 및 테스트
- [ ] VectorStore 실제 구현
- [ ] LLM Client 실제 구현
- [ ] Tool 응답 검증 로직

## 🔗 참고 자료

- [MCP Documentation](https://modelcontextprotocol.io/)
- [Claude Code MCP Guide](https://github.com/anthropics/claude-code)
- [KHW RFP Document](./KHW_RPF.md)

## 💡 팁

1. **개발 중 MCP 서버 재시작**
   - 코드 수정 후 Claude Desktop 재시작 필요

2. **디버깅**
   - `app/core/logging.py` 에서 LOG_LEVEL=DEBUG 설정
   - MCP 서버 로그는 stdout으로 출력됨

3. **복수 MCP 서버**
   - claude_desktop_config.json에 여러 MCP 서버 등록 가능
   ```json
   {
     "mcpServers": {
       "khw": { ... },
       "other-server": { ... }
     }
   }
   ```
