Backend init 2025-11-11 17:42

## 개요
이 프로젝트는 MOBY 서비스용 백엔드 서버입니다.  
사용자 인증, 데이터 수집 및 분석 결과 제공을 위한 RESTful API를 제공합니다.

## 주요 기능
- JWT 기반 사용자 인증 및 권한 관리
- 스케줄링된 데이터 수집 파이프라인
- 분석 결과 및 통계 제공 API
- 운영 모니터링을 위한 헬스체크 엔드포인트

## 개발 환경
- Node.js 20.x
- PostgreSQL 15
- Redis 7
- pnpm 9.x

## 시작하기
1. 의존성 설치
   ```bash
   pnpm install
   ```
2. 환경 변수 설정
   - `.env.example`를 참고해 `.env` 파일을 생성하고 값을 채워주세요.
3. 개발 서버 실행
   ```bash
   pnpm dev
   ```
4. 테스트 실행
   ```bash
   pnpm test
   ```

## 배포
- `main` 브랜치에 머지되면 CI가 자동으로 도커 이미지를 빌드합니다.
- 운영 환경은 Kubernetes로 관리되며 `helm upgrade`를 통해 롤링 업데이트를 수행합니다.

## 문의
운영 관련 문의는 슬랙 `#ai-backend` 채널로 남겨주세요.