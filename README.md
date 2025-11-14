# aischool (백엔드)

## 개요
이 저장소는 MOBY 서비스용 백엔드 서버입니다.
사용자 인증, 데이터 수집 및 분석 결과 제공을 위한 RESTful API를 제공합니다.

## 주요 기능
- JWT 기반 사용자 인증 및 권한 관리
- 스케줄링된 데이터 수집 파이프라인
- 분석 결과 및 통계 제공 REST API
- 운영 모니터링을 위한 헬스체크 엔드포인트

## 요구 사항
- Node.js 20.x
- PostgreSQL 15 (또는 호환 버전)
- Redis 7 (세션/캐시 용도)
- `pnpm` 9.x

## 빠른 시작 (개발)
1. 저장소 폴더로 이동:
   ```powershell
   cd C:\Users\ksa\backend\aischool
   ```
2. 의존성 설치:
   ```powershell
   pnpm install
   ```
3. 환경 변수 설정:
   - `.env.example` 파일을 복사하여 `.env` 파일을 만들고 값을 채우세요.
   - 예시:
     ```text
     PORT=3000
     DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
     REDIS_URL=redis://localhost:6379
     JWT_SECRET=your_jwt_secret
     ```
4. 데이터베이스 마이그레이션(프로젝트에 마이그레이션 스크립트가 있을 경우):
   ```powershell
   pnpm run migrate
   ```
5. 개발 서버 실행:
   ```powershell
   pnpm dev
   ```
6. 테스트 실행:
   ```powershell
   pnpm test
   ```

## 도커(선택)
- 이미지 빌드:
  ```powershell
  docker build -t aischool-backend .
  ```
- 컨테이너 실행:
  ```powershell
  docker run -e DATABASE_URL="..." -p 3000:3000 aischool-backend
  ```

## 배포
- `main` 브랜치에 머지되면 CI가 자동으로 도커 이미지를 빌드하도록 설정되어 있습니다.
- 운영 환경은 Kubernetes로 관리되며 `helm upgrade`로 롤링 업데이트를 수행합니다.

## 환경 변수
- `.env.example`을 참조하세요. 주요 변수:
  - `PORT` — 서버 포트 (기본 3000)
  - `DATABASE_URL` — PostgreSQL 연결 문자열
  - `REDIS_URL` — Redis 연결 문자열
  - `JWT_SECRET` — 인증용 시크릿

## 문제 해결
- 데이터베이스 연결 오류: `DATABASE_URL` 값을 확인하고 DB가 기동 중인지 확인하세요.
- 포트 충돌: `PORT` 값을 변경하거나 해당 포트를 사용 중인 프로세스를 종료하세요.

## 기여
- 버그 리포트나 기능 제안은 이슈로 남겨주세요.
- PR은 `main` 브랜치로 요청하며, 변경 사항은 간단한 설명과 테스트를 포함해주세요.

## 연락처
- 담당자: 프로젝트 팀 (예: `dev-team@example.com`) — 실제 연락처로 바꾸어 주세요.
