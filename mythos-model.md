# 클로드 미토스(Claude Mythos) 모델 조사

> 조사일: 2026-06-08

## 1. 개요

**클로드 미토스(Claude Mythos)**는 Anthropic이 개발한 차세대 대규모 언어 모델이다.
범용 작업 전반에서 강력한 성능을 보이지만, 특히 **컴퓨터 보안 분야**에서 두드러진 능력을 가진 것이 특징이다.

- 존재가 공개적으로 알려진 시점: 2026년 3월 26일 (블로그 초안 유출)
- Anthropic 공식 공개: 2026년 4월 7일
- 일반 상용 모델이 아닌, **게이트(gated) 연구 프리뷰** 형태로 제공

## 2. 이름의 의미

"Mythos(미토스)"는 그리스어로 "이야기" 또는 "신화"를 뜻한다.
AI가 단순히 정보를 처리하는 수준을 넘어, 풍부한 서사를 이해하고 만들어낼 수 있게 되었다는
의미를 담아 명명되었다.

## 3. 핵심 역량

- **제로데이(zero-day) 취약점 탐지 및 익스플로잇 생성**: 실제 오픈소스 코드베이스에서
  알려지지 않은 취약점을 찾아내고 익스플로잇을 만들어낸다.
- **클로즈드소스 익스플로잇 리버스 엔지니어링**: 비공개 소프트웨어의 알려진 취약점을
  실제 공격 코드로 전환한다.
- **익스플로잇 체인 구성(exploit chain construction)**: 작은 공격 프리미티브들을 연결해
  동작하는 익스플로잇을 구성한다. 예) use-after-free 버그를 임의 읽기/쓰기 프리미티브로
  발전시켜 시스템을 완전히 장악.
- 복잡한 논리 문제에 대한 향상된 추론 능력
- 긴 문서 처리를 위한 넓은 컨텍스트 윈도우
- 향상된 코딩 능력
- 한국어를 포함한 다국어 능력 강화

## 4. Project Glasswing (프로젝트 글래스윙)

Mythos Preview를 활용해 세계의 핵심 소프트웨어를 보호하기 위한 이니셔티브.

- 참여 기업·기관이 자사 소프트웨어와 시스템의 치명적 취약점을 찾아 수정하도록 지원
- Claude Mythos Preview는 이 게이트형 연구 프리뷰("Project Glasswing")로만 제공되며,
  일반 대중에게는 공개되지 않음
- 방어적 보안(defensive security) 목적의 제한적 연구 프로그램으로 운영

## 5. 의의

AI가 보안 공격에 활용되면서 공격은 "더 빠르고, 더 자동화되며, 동시에 더 많은 취약점을
악용할 수 있게" 되고 있다. Mythos는 사이버 보안의 새로운 시대를 예고하는 모델로 평가받으며,
공격자보다 앞서기 위해 산업계가 채택해야 할 관행을 준비하는 데 목적이 있다.

## 6. 참고 자료

- [Claude Mythos Preview — red.anthropic.com](https://red.anthropic.com/2026/mythos-preview/)
- [What is Claude Mythos? — Pluralsight](https://www.pluralsight.com/resources/blog/ai-and-data/what-is-claude-mythos)
- [Claude Mythos — Wikipedia](https://en.wikipedia.org/wiki/Claude_Mythos)
- [Project Glasswing: what Mythos showed us — Cloudflare Blog](https://blog.cloudflare.com/cyber-frontier-models/)
- [미토스(Mythos)란 무엇인가 — AhnLab](https://www.ahnlab.com/ko/contents/content-center/36153)
- [클로드 미토스 프리뷰 — 코인데스크코리아](https://www.coindeskkorea.com/4573)
- [미토스에 놀란 세계 — ZDNet Korea](https://zdnet.co.kr/view/?no=20260412123017)
