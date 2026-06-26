# Agent System v2 — 재설계 기획안 (Re-architecture Design) · rev.4

- 작성일: 2026-06-26 (KST) / 개정: **rev.4** (Kay 미해결 후속결정 6 + 내구성 요구 반영)
- 입력: 기존 기획안 + 소스 다이어그램 + 현재 코드베이스 + `~/llm_wiki` 규약 + Kay 안건(4 + 14 + 7) + Claude/Codex 공식 문서·소스
- 상태: **설계 개정 (구현 전, Kay 리뷰 대기)** · 접근: 목표 아키텍처 + 단계적 마이그레이션

> **rev.4 변화**: ① 라이브 로그 **SSE 확정**. ② 기본 권한 **`auto` 모드**. ③ **Rate-limit 자동 재개**: 공식 문구로 감지 → 로그 스냅샷 → **Claude Haiku가 리셋시각 파싱·cron 생성** → UI에 티켓#·재시작시각 표시 → 리셋 후 자동 resume(§14). ④ 모델 레지스트리 **수동 config + Single Source of Truth**. ⑤ 스킬 유사탐색 소스 = **설치 plugin + 마켓 레지스트리 + Web Search**. ⑥ 위키 maintainer **Claude 고정**. ⑦ **데이터 내구성/Fail-safe**: 정전·WSL 강제종료로 DB·컨테이너·tmux 전멸 대비 — /mnt/k 스냅샷 + 복구 루틴 + resumable run(§15).

---

## 0. 프로젝트의 두 목적
| 목적 | 내용 | 영향 |
|---|---|---|
| 주 | Kay 작업 편의 실용 시스템 | 단일 사용자 로컬, Kay 승인 게이트 |
| 부 | **Web Dev → AX Engineer 커리어 전환** 포트폴리오 | **LangChain·RAG·LangGraph 의도적 채택** |

## 1. 재설계 동기
E2E 검수 중 In Progress 드래그 멈춤 → 근본원인: 자동화가 상태가 아니라 **큐**로 구동(전이는 상태만 바꾸고 run 미생성). rev.2~4로 트리거·오케스트레이션·실행·메모리·내구성을 재설계.

---

## 2. Decision Log

| # | 결정 | 선택 | 근거 |
|---|---|---|---|
| D1 | 목적 | 전면 재설계 + 커리어 학습가치 | §0 |
| D2 | 오케스트레이션 | **Hermes 제거. LangGraph 런타임 + LangChain 추상화** | 안건1·2·8 |
| D3 | 실행 방식 | **인터랙티브 CLI 세션을 전용 tmux 새 윈도우**에서(print/exec 아님) | 검수1 |
| D4 | 트리거 | digestible 진입=자동 navigate+enqueue, 큐=동시성 버퍼 | 멈춤버그 |
| D5 | 에이전트 역할 | 2종: Navigator(라우팅) / Executor(수행) | 안건3 |
| D6 | 세분화 | 부모→자식, 재귀, Navigator가 PM/CTO+계획 plugin 라우팅 | 안건3a |
| D7 | persona↔brain | 창의=Codex, 기술=Claude | 안건3b |
| D8 | Watcher | 시작·진행·권한·완료 감시 → 완료 시 윈도우 kill·다음 작업 | 검수2 |
| D9 | **권한 기본** | **`auto` permission mode** (Claude `auto`/Codex workspace-write·on-request). 에이전트별 scope UI. 공식 플래그로 사전인가 | 후속2·검수3 |
| D10 | **Failure 분류** | 일시(429/스로틀/통신)=재시도→폴백; **사용량한도=감지→Haiku cron 재개**(§14); hang=kill | 검수4·후속3 |
| D11 | **모델 선택** | 공식 문서 기반 picker(기본=최신). **레지스트리는 수동 config + SSOT(한 곳 정의·참조)** | 검수5·후속4 |
| D12 | 프로젝트 관리 | Project CRUD(slug/title/보드템플릿) | 검수6 |
| D13 | UI/UX | minimal + 1080p~4K 반응형 | 검수7 |
| D14 | 벡터스토어 | pgvector (Chroma 백로그) | 검수9 |
| D15 | LangGraph checkpointer | Postgres | 검수10 |
| D16 | 위키 maintainer | **Claude 고정** (opus + 최대 effort) | 검수11·후속6 |
| D17 | 스킬 자기진화 | 기존 유사 우선 제안→수락=설치/거부=생성. **유사탐색 = 설치 plugin + 마켓 레지스트리 + Web Search** | 검수12·후속5 |
| D18 | 부모 자동완료 | 기본 ON + UI 토글 | 검수14 |
| D19 | **라이브 로그** | **SSE 확정** (폴링 폴백) | 후속1 |
| D20 | **데이터 내구성** | **/mnt/k 스냅샷 + 복구 루틴 + resumable run**(정전·WSL drop 대비) | 검수7(추가) |
| D21 | Rate-limit 파싱 | **공식 감지문구는 SSOT 패턴 config, 리셋시각은 Haiku가 파싱**(문구 릴리스 변동 대비) | 후속3 |

---

## 3. 핵심 멘탈모델
> Kanban 티켓 = 작업 단위(재귀 세분화). **LangGraph StateGraph**가 라이프사이클 런타임(LLM 아님) — 결정 노드→**Navigator**, 작업 노드→**Executor**. Executor는 **전용 tmux 새 윈도우의 인터랙티브 CLI**로 돌고 **Watcher**가 감시·관리. **LangChain**이 CLI/RAG/프롬프트 추상화, **RAG over LLM Wiki**가 장기기억 주입. 모든 전이는 raw 기록→ingest 합성→반복교훈 Skill화→자동 적용. **상태는 Postgres에 durable(라이프사이클 checkpointer 포함)**, 산출물·로그는 /mnt/k에 저장 → 정전/WSL drop에도 복구 가능.

## 4. 컴포넌트 아키텍처
```
                                HOST (WSL2 / Linux)
 +--------------------------------------------------------------------------------+
 |  Browser ── http/SSE ──> web (React/Vite, 반응형)                               |
 |                              v                                                  |
 |                           api (FastAPI) ───────────────┐ SSE run-log            |
 |                              v                          v                        |
 |                  ┌────────────────────────┐    Postgres + pgvector              |
 |                  │ Orchestrator(LangGraph)│◄──►(상태·벡터·레지스트리·scheduled  |
 |                  │ StateGraph + PG ckpt    │     jobs ; 라이프사이클 checkpoint) |
 |                  └───┬───────────┬─────────┘         ^                           |
 |        LangChain+RAG │           │ enqueue           │ embed wiki                |
 |        ┌─────────────┴──┐    queue_items       ┌─────┴──────┐                   |
 |        │ Navigator(LLM) │        │             │ RAG(pgvec) │                   |
 |        └────────────────┘        v             └────────────┘                   |
 |                          Host 실행 데몬: tmux 전용세션 새 윈도우 →               |
 |                            인터랙티브 CLI(권한 사전인가) → pane→run.log          |
 |                                    │                                             |
 |               Watcher: 윈도우 감시(시작/진행/권한/완료/실패) → 완료 시 kill·다음 |
 |                            │ rate-limit 감지 시 → Haiku 파서 → cron 재개(§14)    |
 |  Scheduler ── cron ──> ingest(02:00)/audit(월말) + **snapshot(주기)**(§15)       |
 |  Recovery(부팅): 스냅샷 복구 + run 재조정 + cron 재무장(§15)                      |
 |  host mounts: /mnt/k/WRITTEN_BY_CODEX · /WRITTEN_BY_CLAUDE · /WSL_volume(스냅샷) · /home/kay/llm_wiki |
 +--------------------------------------------------------------------------------+
```

(컴포넌트 표는 rev.3과 동일 + Recovery/Snapshot 서비스, Rate-limit 재개기 추가 — §14·§15.)

---

## 5. 오케스트레이션 — LangGraph StateGraph
상태 = `{ticket, navigator_decision, run, review, retries, rate_limit_until, cli_session_id}`. **Postgres checkpointer**로 durable. 노드: intake→navigate(subdivide|execute)→subdivide/ dispatch→watch→review→complete→ingest-memory. 세분화·리뷰NO·실패는 조건부 엣지로 분기.

### 5.1 Failure 분류 (검수4·후속3, 공식 문구 기반)
| 분류 | 감지(공식 문구/신호) | 전략 |
|---|---|---|
| **일시 통신/용량** | Claude `API Error: Request rejected (429)`, `Server is temporarily limiting requests (not your usage limit)`; Codex `Rate limit reached for …`(raw API, 상대시간); 스트림 끊김 | **지수 백오프 재시도 N회** → 실패 시 **fallback brain** → 그래도면 **Blocked + Kay 알림** |
| **사용량 한도(플랜)** | Claude `You've hit your (session\|weekly\|Opus) limit · resets …`; Codex `You've hit your usage limit …`(또는 `codex exec --json`의 `UsageLimitExceeded`) | **§14 Rate-limit 자동 재개 메커니즘** |
| **무한 hang** | heartbeat/timeout 초과 | 윈도우 kill → 재시도/Blocked |
| **권한 교착** | Watcher가 pane에서 권한 프롬프트 패턴 | 사전인가(§11)로 대부분 차단; 뜨면 정책 자동응답 or Kay 에스컬레이션 |

> 감지 문구는 릴리스마다 바뀔 수 있으므로 **SSOT 패턴 config(`ratelimit_patterns`)** 로 관리하고, 정확한 리셋 시각은 §14의 Haiku 파서가 담당(문자열 매칭에 과의존 금지).

---

## 6. 에이전트 역할 2종
- **(a) Navigator**: persona + skill/plugin set + agent(brain) + **모델** 선택, 세분화 라우팅 포함(프로젝트 티켓→PM/CTO+계획 plugin like `superpowers`/`gstacks`). LangChain chain(RAG 주입→CLI LLM→구조화 파서→`navigator_decisions`).
- **(b) Executor**: 전용 tmux 새 윈도우 인터랙티브 CLI로 산출물 생성.

| brain | 성격 | persona |
|---|---|---|
| Codex | 창의 | PM, Marketer, Accountant, Strategist, CS Manager, Researcher, QA(E2E) |
| Claude | 기술 | CTO, Full Stack Developer, DevOps, Android/iOS, AI Engineer, MLOps, Data Engineer, QA(Unit), SecOps |

## 7. 트리거 & digest_policy
`status_blocks.digest_policy`: `none|agent_execute`. `agent_execute`(In Progress) 진입 → `navigate(execute)→dispatch`. 세분화는 명시 트리거(재귀). 큐=per-brain 동시성 버퍼.

## 8. 티켓 세분화
`tickets.parent_ticket_id`(재귀). Kay 트리거→Navigator(PM/CTO+계획 plugin)→Executor 자식 제안→Kay 승인→Todo 생성. **부모 자동완료 기본 ON + UI 토글**(`auto_complete_parent`).

## 9. End-to-End
```
프로젝트 생성→보드템플릿→Triage 티켓 → (세분화 트리거→Navigator→Executor 제안→승인→자식, 재귀)
→ leaf를 In Progress 드래그 → navigate(execute): RAG 주입·persona/skill/agent/모델 결정 → dispatch
→ Host 데몬: tmux 새 윈도우 인터랙티브 CLI(권한 사전인가) → pane 라이브(SSE)
→ Watcher: 시작/진행/권한/완료 감시 (실패=§5.1, 사용량한도=§14) → 완료 시 윈도우 kill → Reviewing → 다음
→ Kay 리뷰: YES=Completed / NO=코멘트 접어 재실행
→ 모든 전이 raw 기록 → ingest(Claude opus) wiki 합성·outcome·스킬후보(§16)
→ 자식 전부 완료 → 부모 자동완료(토글)
```

## 10. 실제 실행 — 인터랙티브 tmux + Watcher (검수1·2)
- **Dispatch**: 데몬이 `agent_runs(queued)` 폴링 → `tmux new-window -t asv2 -n run-<id>` → 인터랙티브 CLI를 권한 사전인가(§11)·모델(§12)로 시작:
  - Claude: `claude --model <id> --permission-mode auto` (+ `settings.json` allow/deny)
  - Codex: `codex --model <id> --sandbox workspace-write --ask-for-approval on-request` (또는 `--profile`)
  - prompt.md를 입력으로, `tmux pipe-pane`으로 `runs/<id>/run.log`(/mnt/k) 적재.
- **Watcher 상태머신**(`tmux capture-pane` 폴링): 시작성공→`running` / 진행→유지 / 권한 프롬프트→§11 / **완료(sentinel+idle)→윈도우 kill→Reviewing→다음** / 에러·끊김·timeout→§5.1 / 사용량한도 문구→§14. 데몬은 finished 마크 안 함(완료 판정=Watcher).
- `ASV2_AGENT_MODE=simulated`: 윈도우 없이 결정적 산출물(동일 계약).

## 11. Agent 권한 / 오토모드 — 공식 문서 기반 (검수3·후속2)
> Shift+Tab 수작업 대신 **세션 시작 시 공식 플래그/설정으로 사전 인가**. **기본 = `auto`**.
- **Claude Code**: `--permission-mode` 값 `default|acceptEdits|plan|auto|dontAsk|bypassPermissions`. **기본 `auto`**(거의 전부 자동 + 백그라운드 안전성 검사). 단 `defaultMode:"auto"`는 프로젝트/로컬 settings에서 무시(v2.1.142+) → **user-level `~/.claude/settings.json`**에 설정; 계정 요건 미충족 시 `acceptEdits`로 폴백. scope 규칙 `permissions.allow/deny/ask`(deny>ask>allow), 문법 `Bash(npm run test:*)`/`Read(.env)`/`Edit(/src/**)`.
- **Codex**: `approval_policy`(`untrusted|on-request|never`) × `sandbox_mode`(`read-only|workspace-write|danger-full-access`). "auto" 등가 = `--sandbox workspace-write --ask-for-approval on-request`. config.toml/프로필 파일(`$CODEX_HOME/<name>.config.toml`).
- **UI**: 보드/프로젝트/에이전트 단위 권한 프리셋·규칙 편집 → API가 `settings.json`/`config.toml`로 기록 → 데몬이 그 설정으로 세션 시작. 런타임 예외 프롬프트는 Watcher가 `tmux send-keys` 폴백.
- 출처: code.claude.com/docs/en/{permission-modes,permissions,settings,cli-reference}; developers.openai.com/codex/{agent-approvals-security,config-reference,config-advanced}

## 12. 모델 레지스트리 & 선택 UX — 공식 문서 기반 (검수5·후속4)
> 정확한 모델명 암기 불필요. 모든 선택 지점(기능/persona/티켓/run)에 picker, **기본=최신**. **MVP는 수동 config이되 Single Source of Truth**(한 모듈/테이블에 정의하고 어디서나 참조 — 유지보수 용이).

**Claude (Claude Code)**: `opus`=`claude-opus-4-8`(기본·최신, `[1m]` 가능) / `sonnet`=`claude-sonnet-4-6` / `haiku`=`claude-haiku-4-5` / `fable`=`claude-fable-5`. 설정 `--model`·`/model`·settings `model`.
**Codex (Codex CLI)**: `gpt-5.5`(기본·최신) / `gpt-5.4` / `gpt-5.4-mini` / `gpt-5.3-codex-spark`(Pro). effort `model_reasoning_effort=minimal|low|medium|high|xhigh`. (`gpt-5.x-codex`·`gpt-5.2`/`gpt-5.3-codex` deprecated.)

- 구현: SSOT 정의(`config/models.*` 또는 `model_registry` 테이블, 필드 brain·id·display·is_latest·is_default·effort·source_url)를 한 곳에 두고 BE/FE가 참조. Navigator 결정에도 모델 필드(override 가능). 갱신은 수동(문서 변경 시 한 곳만 수정).
- 출처: code.claude.com/docs/en/model-config; developers.openai.com/codex/models

## 13. 라이브 런 뷰 — SSE 확정 (후속1)
- 데몬 pane → `runs/<id>/run.log`. **전송 = SSE**(`GET /runs/{id}/stream`, `text/event-stream` 서버 푸시; 거의 즉시, 변화 시에만 전송). 연결 불가/끊김 시 **폴링 폴백**(`GET /runs/{id}/log?offset=`).
- UI: In-Progress 카드 펼치면 stdout 실시간 tail + `cancel`/`open full log`.

## 14. Rate-limit 자동 재개 메커니즘 (검수4·후속3, 공식 소스 기반)
> 사용량 한도에 걸린 작업을 사람이 안 건드려도 리셋 후 알아서 재시작.

**흐름**:
1. **감지(Watcher)** — pane 텍스트를 **SSOT 패턴(`ratelimit_patterns`)** 과 매칭:
   - Claude: `You've hit your (session|weekly|Opus) limit · resets …` (출처: code.claude.com/docs/en/errors.md)
   - Codex: `You've hit your usage limit …` / 머신리더블 `codex exec --json`의 `UsageLimitExceeded` (출처: github.com/openai/codex `protocol/src/error.rs`)
   - (일시 429/스로틀은 §5.1으로 분기 — 한도 아님.)
2. **스냅샷** — 해당 로그 블록을 캡처(`runs/<id>/ratelimit-<n>.log`).
3. **Haiku 파싱·스케줄** — **Claude Haiku 최신(`claude-haiku-4-5`)** 헤드리스로 스냅샷에서 리셋시각 추출:
   ```
   claude -p "<snapshot>" --model haiku --output-format json --json-schema
     '{"type":"object","properties":{"reset_time":{"type":"string","format":"date-time"},
       "limit_type":{"type":"string"}},"required":["reset_time","limit_type"]}'
   ```
   → `reset_time`(ISO8601)·`limit_type` 획득. (Codex는 가능하면 `resets_at` epoch 직접 사용이 더 정확.) 그 시각에 재개하는 **cron job 생성**(durable: `scheduled_jobs` 테이블에 기록 후 OS cron 등록 — §15와 연계).
4. **UI 알림** — run을 `rate_limited`·`rate_limit_until=reset_time`로 표시하고, **티켓#·재시작 예정시각**을 카드 코멘트/알람으로 노출.
5. **리셋 후 자동 resume** — cron 발화 → LangGraph 재개: 가능하면 CLI 세션 resume(Claude `--resume <cli_session_id>`/`--continue`, Codex `codex exec resume --last`), 세션 유실 시 durable 컨텍스트로 **신규 re-dispatch**. 큐는 그동안 다른 brain 작업 계속.

---

## 15. 데이터 내구성 / Fail-safe (검수 추가7)
> **위협**: 이 기기는 정전·WSL 인스턴스 강제 drop 등으로 **DB·Docker 컨테이너·tmux 세션이 통째로 삭제**되는 일이 잦음.

**원칙**: ① 상태의 단일 진실원천(Postgres)을 주기적으로 **WSL 밖(/mnt/k)** 으로 스냅샷, ② 산출물·로그는 처음부터 /mnt/k에 저장, ③ run은 **재개 가능(idempotent)** 하게 설계, ④ 부팅 시 **복구 루틴**.

| 대상 | 전략 |
|---|---|
| **Postgres(상태·checkpointer·레지스트리)** | 라이브 PGDATA는 리눅스-네이티브 볼륨(성능·fsync). **주기적 `pg_dump` 스냅샷을 `/mnt/k/WSL_volume/asv2/snapshots/`** 로(예: 5–15분 + Completed/리뷰 등 핵심 전이 직후). 부팅 시 DB 비어있으면 **최신 스냅샷 자동 복구**. (선택: WAL 아카이빙으로 RPO 단축.) → drvfs(/mnt/k) 위에서 PGDATA 직접 구동은 fsync/락 문제로 **비권장**, 스냅샷 방식 채택 |
| **산출물·run 로그** | 이미 `/mnt/k/WRITTEN_BY_*`·`runs/<id>/` (Windows측) → WSL drop에도 생존. SSOT 유지 |
| **tmux 세션(휘발·복구 불가)** | 죽으면 끝 → **resumable run 설계**. 부팅/복구 시 `agent_runs(dispatched/running)` 중 **tmux 윈도우 부재면 `interrupted` 처리 후 재-enqueue**. CLI 세션 resume 가능하면(`--resume`/`codex exec resume`) 이어가고, 아니면 durable 컨텍스트로 신규 re-dispatch |
| **Docker 컨테이너** | compose로 재생성(상태 없음). 상태는 위 Postgres/파일에만 |
| **cron job(rate-limit 재개 등)** | OS crontab은 wipe될 수 있으므로 **`scheduled_jobs` 테이블에 스케줄을 durable 저장** → 복구 시 **cron 재무장**(re-arm) |

**복구 서비스(부팅 루틴)**: (a) DB 스냅샷 복구(필요 시) → (b) run 재조정(tmux 현실과 대조, interrupted 재투입) → (c) `scheduled_jobs`로 cron 재무장 → (d) `rate_limit_until` 지난 run 즉시 재개. LangGraph checkpointer(Postgres)로 워크플로우는 마지막 체크포인트부터 이어짐.

**스냅샷 config(SSOT)**: 간격·보존수·대상경로(`/mnt/k/WSL_volume/asv2/snapshots/`) 한 곳 정의.

---

## 16. 장기 메모리 & 자기진화 — LLM Wiki 루프 (안건4·검수11·12)
`~/llm_wiki` = Karpathy 패턴(raw/wiki/schema, Ingest/Query/Lint), Decision `outcome:good|mixed|bad`+Review. agent-system-v2는 이미 raw 이벤트 기록 중.
- **Ingest(02:00 KST)**: 위키 maintainer = **Claude 고정(opus + 최대 effort)** 가 규약대로 raw→wiki 합성.
- **Query(RAG)**: Navigator가 wiki만 검색(§17).
- **Lint(월말 04:00)**: 모순·orphan·broken·stale·ingest gap.

### 16.1 자기진화 스킬 — 기존 우선 → 설치/생성 (검수12·후속5)
```
실행→리뷰(만족/실수/개선요청)→raw→ingest(outcome·반복패턴 concept화)
→ 임계치 넘은 교훈에 대해, 먼저 기존 유사 스킬/플러그인 탐색:
   소스 = ① 설치된 plugin 목록 ② 마켓/플러그인 레지스트리 ③ Web Search
→ 유사한 게 있으면 "이름 + 기능 설명" 포함 제안(UI/코멘트)
     · Kay 수락 → CLI로 설치   · Kay 거부 → 새 스킬 생성(superpowers 호환)
→ 없으면 바로 신규 생성 제안 → 활성화는 Kay 승인 게이트
→ 다음 유사 티켓에서 Navigator가 RAG로 자동 선택·주입
```
기억 대상: ① 하면 안 될 실수 ② 진행 중 개선요청 ③ 만족한 방식.

## 17. RAG 설계 (검수9)
**pgvector**(기존 Postgres). 임베딩 = **wiki 합성 페이지**(규약상 raw 직접 검색 금지). 체인: `retriever(pgvector)→(rerank)→context packet→CLI LLM`. 주입 2곳: Navigator 결정 / Executor 프롬프트. ingest 직후 재임베딩.

## 18. 프로젝트 관리 (CRUD) (검수6)
`Project`(보드 위 계층): 신규 생성, slug/title 자유, 보드 템플릿 선택. Project=1+Board, 티켓번호 prefix. CRUD: 생성/조회/수정/아카이브.

## 19. UI / UX & 반응형 (검수7)
Minimal + 정보밀도. **1920×1080~3840×2160** 유동 그리드(해상도에 따라 1~3 패널 동시: 보드/드로어/큐/라이브로그), rem 스케일·고DPI. 드래그=실행 모델 시각화(디스패치 배지, ●live, 권한/모델 인라인).

## 20. 데이터 모델 (기존 진화)
| 테이블 | 변경 |
|---|---|
| `projects`(신규) | id, slug, title, description, board_template_id, status, created_at |
| `boards` | `project_id` |
| `tickets` | `parent_ticket_id`, `auto_complete_parent`(기본 true) |
| `status_blocks` | `digest_policy`(none/agent_execute) |
| `agent_runs` | `log_path`, 상태 `queued→dispatched→running→rate_limited→interrupted→success/failed/canceled`, `fallback_used`, `rate_limit_until`, `tmux_window`, `cli_session_id` |
| `navigator_decisions` | `task_kind`, `model_id`, `rag_context_refs`, `fallback_used` |
| `subdivision_proposals`(신규) | parent_ticket_id, proposed_children_json, status, created_by |
| `agent_permission_profiles`(신규) | scope, brain, mode, allow_json, deny_json, settings_path |
| `model_registry`(신규, SSOT) | brain, model_id, display_name, is_latest, is_default, effort_options_json, source_url |
| `scheduled_jobs`(신규) | kind(ratelimit_resume/snapshot/ingest…), run_id, fire_at, payload_json, status (cron 재무장용 durable) |
| `wiki_embeddings`(신규, pgvector) | wiki_path, chunk, embedding, page_type, outcome, updated_at |
| `generated_skills`(신규) | slug, source_concept_path, kind(install_existing/new), suggested_ref, body_md, status, risk_level, approved_by |
| `queue_items, status_events, artifacts, wiki_sync_jobs, watcher_events, comments, personas, skills` | 유지 |

## 21. API (변경/추가)
```
GET/POST /projects ; GET/PATCH /projects/{id} ; POST /projects/{id}/archive ; GET /board-templates
POST /tickets/{id}/transition          # agent_execute 진입 시 navigate(execute) 자동
POST /tickets/{id}/subdivide ; GET /tickets/{id}/subdivision ; POST /subdivisions/{id}/approve|reject
POST /tickets/{id}/runs                 # 수동 재디스패치
GET  /runs/{id}/stream (SSE) ; GET /runs/{id}/log?offset=   # 라이브 로그
POST /runs/{id}/resume                  # rate-limit 후(자동도 있음)
GET/PUT /agents/{brain}/permissions ; GET /permission-presets
GET /models?brain=claude|codex          # SSOT, 기본=최신
PATCH /status-blocks/{id}               # digest_policy
GET /skills/generated ; POST /skills/generated/{id}/accept|reject
GET /memory/search?q=
GET /system/snapshots ; POST /system/snapshots          # 내구성 운영
GET /scheduled-jobs                     # cron 재무장 가시화
```

## 22. 마이그레이션 로드맵
| Phase | 내용 | 효과/학습 |
|---|---|---|
| 1 트리거 수정 | digest_policy + 전이-트리거 enqueue (기존 worker/simulated) | **멈춤 즉시 해결** |
| 2 프로젝트 CRUD + 반응형 UI 골격 | projects/보드템플릿, 1080p~4K | 검수6·7 |
| 3 **내구성 기반** | pg_dump 스냅샷→/mnt/k, 부팅 복구 루틴, `scheduled_jobs` | **검수7(추가) — 우선 안정화** |
| 4 LangGraph + 실패정책 | StateGraph, PG checkpointer, §5.1 + §14 rate-limit 재개 | **LangGraph 실전**, 검수4 |
| 5 인터랙티브 tmux + Watcher + 권한/모델 | 새 윈도우 인터랙티브 CLI, 사전인가, 모델 SSOT/picker, Watcher, SSE 로그 | **검수1·2·3·5 핵심** |
| 6 세분화 + Navigator(LangChain) | 재귀 세분화, Navigator chain, 부모 자동완료 | **LangChain 실전** |
| 7 RAG 메모리 | pgvector, 임베딩, 주입 | **RAG 실전** |
| 8 자기진화 + 하드닝 | outcome→스킬(기존우선/생성, plugin+마켓+websearch), 승인 게이트, audit | 진화 완성 |

> Phase 3(내구성)을 앞으로 당김 — 이 기기 특성상 데이터 유실이 잦아 다른 기능보다 먼저 안정화 필요.

## 23. 성공 기준
- [ ] In Progress 드래그 → 자동 실행. 재귀 세분화·leaf 독립 실행.
- [ ] Executor가 전용 tmux 새 윈도우 인터랙티브 CLI로 **권한 프롬프트 없이**(auto) 실행, Watcher가 완료 시 윈도우 kill→다음.
- [ ] 통신/일시 = 재시도·폴백; **사용량 한도 = Haiku가 리셋시각 파싱·cron 생성, UI에 티켓#·재시작시각, 리셋 후 자동 resume**.
- [ ] 모든 모델 선택에 picker(기본=최신), 정의는 SSOT 한 곳.
- [ ] 라이브 로그 **SSE**. 1080p~4K 반응형.
- [ ] **정전/WSL drop 후 부팅 시**: 스냅샷 복구 + 중단 run 재투입 + cron 재무장으로 작업이 이어짐.
- [ ] 전이 raw 기록 → ingest(Claude opus) 합성. 반복교훈 → 기존 유사(설치/마켓/websearch) 제안 또는 생성 → 승인 후 자동 적용.
- [ ] (학습) LangGraph·LangChain·RAG 실경로 작동.

## 24. 비목표
사람 승인 없는 완전 자율(세분화·실행·스킬활성·위험권한 게이트 유지); 멀티테넌트 SaaS; K8s 오토스케일(장기); 외부 통합(Slack/Notion/Jira); 민감 배포/결제/삭제 자동.

## 25. Open Questions (대부분 해소, 잔여)
- `auto` 권한 모드의 계정 요건 미충족 시 폴백 정책 확정(`acceptEdits`?).
- 스냅샷 간격/보존수, WAL 아카이빙 채택 여부(RPO 목표).
- rate-limit cron을 OS cron vs LangGraph 내부 타이머 중 무엇으로(둘 다 `scheduled_jobs` durable 전제).
- CLI 세션 resume 신뢰성(인터랙티브 세션 id 확보 경로) vs 항상 신규 re-dispatch.
- 모델 레지스트리 수동 갱신 주기/담당.
