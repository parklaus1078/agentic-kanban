# `/goal` 구현 프롬프트 — Agent System v2 (rev.4)

> 사용법: 아래 `--- PROMPT ---` 블록을 그대로 복사해 Claude Code의 `/goal`에 붙여넣어 사용. (`/goal`은 4000자 제한 — 이 압축본은 본문 ≈2.95k자라 `in Ultracode` 등 접미를 붙여도 여유 있음.)
> 기준 문서(source of truth): `docs/superpowers/specs/2026-06-26-agent-system-v2-rearchitecture-design.md` (rev.4)

---

--- PROMPT ---

# Goal: Agent System v2를 상세 기획안(rev.4)대로 구현

레포 `/home/kay/agent-system-v2`에서 Agent System v2를 구현하는 시니어 엔지니어다.

## 0. 먼저
1. `docs/superpowers/specs/2026-06-26-agent-system-v2-rearchitecture-design.md`(rev.4) **전체를 읽어라** — 유일한 source of truth. §2 Decision Log(D1–D21)는 구속력 있는 결정, 임의 변경 금지(바꾸려면 Kay에게 근거와 함께 제안).
2. 기존 코드 파악: FastAPI(`apps/api`)+React/Vite(`apps/web`)+Postgres+Compose(`infra/`). **갈아엎지 말고 진화시킨다**(D13).
3. 동기 버그: In Progress 드래그 시 멈춤 — 자동화가 상태 아닌 큐로 구동돼 전이가 run을 안 만듦. Phase 1이 수정.

## 1. 비협상 핵심 결정 (표류 금지)
- **트리거**: `status_blocks.digest_policy=agent_execute`(예 In Progress) 진입=자동 Navigator 결정+run enqueue. 드래그=실행(Run 버튼은 수동 재디스패치만).
- **오케스트레이션**: Hermes 없음. **LangGraph** StateGraph 런타임(LLM 아님), checkpointer=**Postgres**. 결정 노드→Navigator, 작업 노드→Executor. **LangChain**으로 CLI/RAG/프롬프트 래핑(LangChain·LangGraph·RAG 의도적 사용, 우회 금지).
- **역할 2종**: (a)Navigator=persona+skill/plugin+agent+모델 선택(세분화 라우팅 포함) (b)Executor=수행.
- **세분화**: 부모→자식 재귀. Kay 트리거→제안→Kay 승인→생성.
- **persona↔brain**: 창의(PM/Marketer…)=Codex, 기술(CTO/DevOps/Fullstack…)=Claude.
- **실행**: 전용 tmux 새 윈도우의 **인터랙티브 CLI 세션**(print/exec 아님). Host 데몬이 `agent_runs(queued)` 폴링→실행. Watcher가 윈도우 감시(시작/진행/권한/완료)→완료 시 kill→다음.
- **권한**: 시작 시 공식 플래그로 사전 인가(Shift+Tab 수작업 금지). 기본 `auto`(Claude `--permission-mode auto`, user-level 필요·미충족 시 `acceptEdits`; Codex `--sandbox workspace-write --ask-for-approval on-request`). 에이전트별 scope를 UI→설정파일. **권한/모델 세부는 공식 문서 근거**(§11·§12).
- **모델**: 모든 지점에 picker, 기본=최신, 목록은 **SSOT 수동 config**(Claude `claude-opus-4-8`/`-sonnet-4-6`/`-haiku-4-5`/`-fable-5`; Codex `gpt-5.5`/`5.4`/`5.4-mini`).
- **라이브 로그**: SSE+폴링 폴백.
- **장기 메모리**: `~/llm_wiki`(Karpathy) raw에 전이 기록→ingest(maintainer=Claude opus 고정·최대 effort)→RAG(pgvector, wiki만 임베딩)로 Navigator/Executor 주입→반복 교훈 Skill화(유사탐색=설치 plugin+마켓+WebSearch→수락=설치/거부=생성, Kay 게이트).
- **Failure/rate-limit**: 일시(429/스로틀/통신)=재시도→fallback brain→Blocked. 사용량 한도=공식 문구 감지(SSOT 패턴)→로그 스냅샷→Haiku(`claude-haiku-4-5`) `-p --output-format json --json-schema`로 리셋시각 파싱→`scheduled_jobs` cron→UI 티켓#·재시작시각→리셋 후 자동 resume.
- **내구성(필수)**: 정전·WSL drop으로 DB·컨테이너·tmux 전멸 대비. Postgres는 주기 `pg_dump`를 `/mnt/k/WSL_volume/asv2/snapshots/`로(drvfs PGDATA 직접구동 금지), 산출물·로그는 `/mnt/k`, run은 resumable, 부팅 복구 루틴(스냅샷 복구+중단 run 재투입+cron 재무장).

## 2. 단계별 (§22 로드맵, 게이트)
한 번에 다 짜지 말고 **Phase 단위로 구현→검증→보고→대기**.
- **Phase 1(먼저 단독)**: `digest_policy` 추가 + `lifecycle.transition_ticket`이 `agent_execute` 진입 시 Navigator 결정+run enqueue 자동 수행(기존 worker/simulated 재사용). 멈춤 해소·드래그=실행 검증 후 멈춰 보고.
- Phase 2~8은 §22 순서대로 동일 사이클.

## 3. 규율
- 기존 패턴 따르고 변경은 작고 외과적으로(무관 리팩터링 금지). 가능하면 TDD(실패 테스트→구현→통과, 기존 `apps/api/tests` 깨지 마라). **검증 후 보고**(테스트/앱 실제 실행, §23 기준, 출력 근거; 실패면 실패라고). 커밋/푸시는 Kay 지시 때만(기본 브랜치면 먼저 브랜치). 위험·비가역 작업은 승인 게이트, secret은 레퍼런스만. 막히거나 모호하면 추측 말고 질문(§25는 해당 Phase에서 확정).
- **UI는 minimal·unique하되 UX 최우선**(§19).

## 4. 산출물 (Phase마다)
동작 코드+테스트+마이그레이션(필요시)+§23 충족 근거+짧은 변경 요약.

시작: §0→Phase 1. 기획안 읽고, 현 코드 대조 간단 구현계획 제시 후 Phase 1 착수.

--- END PROMPT ---

---

## 참고 (이 파일 사용자용 메모, `/goal`에는 넣지 말 것)
- `/goal` 4000자 제한 대응 압축본. 본문 ≈2,950자(wc -m) → `in Ultracode` 등 접미 붙여도 여유.
- Phase 1만 시키려면 "## 2" 를 "Phase 1만 구현하고 멈춰라"로 줄여 사용.
- 기준 문서: `docs/superpowers/specs/2026-06-26-agent-system-v2-rearchitecture-design.md` (+ 동일 폴더 HTML).
- 세션 원자료: `~/llm_wiki/.../raw/decisions/2026-06-26-agent-system-v2-rearchitecture.md`, `~/.../raw/notes/2026-06-26-agent-system-v2-session-and-cli-reference.md`.
