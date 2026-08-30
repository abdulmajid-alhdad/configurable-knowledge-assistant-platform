# ruff: noqa: E501
"""FastAPI delivery surface for the portfolio demonstration."""

from typing import TYPE_CHECKING, Any, Protocol

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from knowledge_platform.application.document_rag import DocumentRagService
from knowledge_platform.delivery.conversation_api import create_conversation_router
from knowledge_platform.delivery.product_api import create_management_router
from knowledge_platform.infrastructure.vector_search.store import VectorChunk, VectorSearchStore
from knowledge_platform.modules.document_knowledge.ports import EmbeddingVector
from knowledge_platform.modules.evidence_grounding.domain.contracts import (
    GroundedAnswer,
    InsufficientEvidence,
    PolicyDenied,
    TechnicalFailure,
)
from knowledge_platform.modules.workspace_assistant.domain.security import DataEgressPolicy
from knowledge_platform.reference.yemen_history import build_reference

if TYPE_CHECKING:
    from knowledge_platform.bootstrap.application import ApplicationRuntime


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1)


class AskService(Protocol):
    def ask(self, *, question: str) -> object: ...


def _demo_service() -> AskService:
    workspace, assistant, source, _ = build_reference()

    class Embeddings:
        def embed_query(self, text: str) -> EmbeddingVector:
            return EmbeddingVector((1.0, 0.0))

        def embed_documents(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
            return tuple(EmbeddingVector((1.0, 0.0)) for _ in texts)

    class Model:
        def generate(self, *, question: str, context: str) -> str:
            return "صنعاء مدينة تاريخية في اليمن."

    class DemoService:
        def ask(self, *, question: str) -> object:
            store = VectorSearchStore()
            if "unsupported" not in question.lower():
                store.add(
                    VectorChunk(
                        workspace.id,
                        source.id,
                        "Sanaa is a historic city in Yemen.",
                        "yemen-demo#1",
                        EmbeddingVector((1.0, 0.0)),
                    )
                )
            return DocumentRagService(
                embeddings=Embeddings(),
                vectors=store,
                model=Model(),
                egress=DataEgressPolicy(True),
            ).ask(
                workspace_id=workspace.id,
                assistant_id=assistant.id,
                question=question,
                source_ids=frozenset({source.id}),
            )

    return DemoService()


def _outcome_payload(outcome: object) -> dict[str, Any]:
    if isinstance(outcome, GroundedAnswer):
        return {
            "outcome": "GroundedAnswer",
            "answer": outcome.answer,
            "evidence": [
                {
                    "source_id": str(item.source_id.value),
                    "content": item.content,
                    "provenance_locator": item.provenance_locator,
                }
                for item in outcome.evidence
            ],
        }
    if isinstance(outcome, InsufficientEvidence):
        return {"outcome": "InsufficientEvidence", "reason": outcome.reason}
    if isinstance(outcome, PolicyDenied):
        return {"outcome": "PolicyDenied", "reason": outcome.reason}
    if isinstance(outcome, TechnicalFailure):
        return {"outcome": "TechnicalFailure", "reason": "request could not be completed"}
    return {"outcome": "TechnicalFailure", "reason": "request could not be completed"}


def create_app(
    service: AskService | None = None,
    *,
    runtime: "ApplicationRuntime | None" = None,
) -> FastAPI:
    application = FastAPI(title="Configurable Knowledge Assistant Platform")
    query_service = service or _demo_service()
    if runtime is not None:
        application.include_router(create_management_router(runtime.management_services()))
        application.include_router(create_conversation_router(runtime.management_services()))

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "knowledge-platform"}

    @application.get("/ready")
    def ready() -> dict[str, str]:
        if runtime is None:
            return {"status": "ready", "mode": "demo"}
        return {"status": "ready", "mode": runtime.settings.mode}

    @application.get("/", response_class=HTMLResponse)
    def demo() -> str:
        return """<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Yemen History Assistant</title>
<style>
:root{color-scheme:light;--ink:#172033;--muted:#5f6b7a;--accent:#176b87;--line:#dbe4ec;--panel:#fff}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:#f3f6f8;color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
.shell{max-width:920px;margin:auto;padding:1rem}.topbar{display:flex;justify-content:space-between;align-items:center;padding:1rem 0;border-bottom:1px solid var(--line)}
.brand{display:flex;gap:.75rem;align-items:center}.mark{display:grid;place-items:center;width:2.5rem;height:2.5rem;border-radius:12px;background:var(--accent);color:white;font-weight:700}.eyebrow{margin:0;color:var(--muted);font-size:.82rem}.brand h1{margin:.1rem 0;font-size:1.15rem}.status{display:flex;gap:.4rem;align-items:center;color:var(--muted);font-size:.85rem}.dot{width:.55rem;height:.55rem;border-radius:50%;background:#2d9b68}
.panel{margin:2.5rem auto 1rem;padding:clamp(1.25rem,4vw,2.5rem);background:var(--panel);border:1px solid var(--line);border-radius:20px;box-shadow:0 12px 35px #17203312}.panel h2{margin:0;font-size:clamp(1.5rem,3vw,2.2rem)}.intro{color:var(--muted);max-width:55ch;line-height:1.7}
label{display:block;margin-top:1.5rem;font-weight:650}textarea{display:block;width:100%;min-height:8rem;margin:.6rem 0;padding:1rem;border:1px solid #bdccd8;border-radius:12px;font:inherit;line-height:1.7;resize:vertical}textarea:focus,button:focus-visible{outline:3px solid #8bd0df;outline-offset:2px}button{border:0;border-radius:10px;padding:.8rem 1.25rem;background:var(--accent);color:white;font:inherit;font-weight:700;cursor:pointer}button:disabled{cursor:wait;opacity:.65}.hint{color:var(--muted);font-size:.85rem}
.result{margin-top:1rem}.result:empty{display:none}.outcome{padding:1.2rem;border:1px solid var(--line);border-radius:14px}.outcome h3{margin:0 0 .55rem}.outcome p{line-height:1.7}.answer{font-size:1.1rem;line-height:1.9}.evidence-list{display:grid;gap:.7rem;margin-top:1rem}.evidence{padding:1rem;border:1px solid var(--line);border-radius:12px;background:#f8fafb}.evidence-content{margin:0 0 .65rem;line-height:1.7}.technical{border-color:#e7c7c7;background:#fff8f8}.warning{border-color:#e7d8aa;background:#fffaf0}.meta{color:var(--muted);font-size:.82rem;direction:ltr;unicode-bidi:plaintext;overflow-wrap:anywhere}
@media(max-width:600px){.topbar{align-items:flex-start;gap:1rem}.status{white-space:nowrap}.panel{margin-top:1.25rem}}
</style></head><body><div class="shell"><header class="topbar"><div class="brand"><div class="mark" aria-hidden="true">م</div><div><p class="eyebrow">&#1575;&#1604;&#1605;&#1587;&#1575;&#1593;&#1583; &#1575;&#1604;&#1605;&#1593;&#1585;&#1601;&#1610;</p><h1>&#1605;&#1587;&#1575;&#1593;&#1583; &#1578;&#1575;&#1585;&#1610;&#1582; &#1575;&#1604;&#1610;&#1605;&#1606;</h1></div></div><div class="status"><span class="dot" aria-hidden="true"></span>Demo ready</div></header>
<main class="panel"><h2>&#1575;&#1587;&#1571;&#1604; &#1593;&#1606; &#1578;&#1575;&#1585;&#1610;&#1582; &#1575;&#1604;&#1610;&#1605;&#1606;</h2><p class="intro">&#1573;&#1580;&#1575;&#1576;&#1575;&#1578; &#1605;&#1587;&#1578;&#1606;&#1583;&#1577; &#1573;&#1604;&#1609; &#1571;&#1583;&#1604;&#1577; &#1605;&#1587;&#1578;&#1585;&#1580;&#1593;&#1577; &#1605;&#1606; &#1575;&#1604;&#1605;&#1589;&#1583;&#1585; &#1575;&#1604;&#1578;&#1580;&#1585;&#1610;&#1576;&#1610;.</p><form id="ask-form"><label for="question">&#1587;&#1572;&#1575;&#1604;&#1603;</label><textarea id="question" required placeholder="&#1605;&#1578;&#1609;...">&#1605;&#1575; &#1578;&#1575;&#1585;&#1610;&#1582; &#1589;&#1606;&#1593;&#1575;&#1569;&#1567;</textarea><button id="ask" type="submit">&#1575;&#1587;&#1571;&#1604; &#1575;&#1604;&#1605;&#1587;&#1575;&#1593;&#1583;</button><span class="hint">&#1575;&#1590;&#1594;&#1591; Enter بعد كتابة السؤال</span></form><section id="result" class="result" aria-live="polite"></section></main></div>
<script>
const form=document.querySelector('#ask-form'),question=document.querySelector('#question'),button=document.querySelector('#ask'),result=document.querySelector('#result');
const text=(tag,value,cls,direction)=>{const node=document.createElement(tag);node.textContent=value;if(cls)node.className=cls;if(direction)node.dir=direction;if(cls==='answer'||cls==='evidence-content')node.dir='auto';if(cls==='meta')node.dir='ltr';return node};
function render(data){result.replaceChildren();const card=document.createElement('article');card.className='outcome';
if(data.outcome==='GroundedAnswer'){card.append(text('h3','الإجابة'));card.append(text('p',data.answer,'answer'));card.append(text('h3','الأدلة والمصادر'));const list=document.createElement('div');list.className='evidence-list';(data.evidence||[]).forEach(item=>{const evidence=document.createElement('div');evidence.className='evidence';evidence.append(text('p',item.content,'evidence-content'));evidence.append(text('div','المصدر: '+item.provenance_locator,'meta'));evidence.append(text('div','Source ID: '+item.source_id,'meta'));list.append(evidence)});card.append(list)}else if(data.outcome==='InsufficientEvidence'){card.classList.add('warning');card.append(text('h3','لا توجد أدلة كافية'));card.append(text('p','لا تتوفر أدلة مناسبة للإجابة عن هذا السؤال.'))}else if(data.outcome==='PolicyDenied'){card.classList.add('warning');card.append(text('h3','تعذر السماح بالطلب'));card.append(text('p','لا تسمح سياسة الوصول بإكمال هذا الطلب.'))}else{card.classList.add('technical');card.append(text('h3','تعذر إكمال الطلب'));card.append(text('p','حدث خطأ آمن أثناء معالجة السؤال. حاول مرة أخرى.'))}result.append(card)}
form.addEventListener('submit',async event=>{event.preventDefault();if(!question.value.trim()){result.replaceChildren(text('p','يرجى كتابة سؤال أولاً.','outcome warning'));question.focus();return}button.disabled=true;button.textContent='جارٍ البحث…';result.replaceChildren();try{const response=await fetch('/api/demo/ask',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({question:question.value})});render(await response.json())}catch(_){render({outcome:'TechnicalFailure'})}finally{button.disabled=false;button.textContent='اسأل المساعد'}});
</script></body></html>"""

    @application.post("/api/demo/ask")
    def ask_demo(payload: AskRequest) -> JSONResponse:
        try:
            return JSONResponse(_outcome_payload(query_service.ask(question=payload.question)))
        except Exception:
            return JSONResponse(
                {"outcome": "TechnicalFailure", "reason": "request could not be completed"},
                status_code=500,
            )

    return application


app = create_app()
