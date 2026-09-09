# ruff: noqa: E501
"""FastAPI delivery surface for the portfolio demonstration."""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from knowledge_platform.application.access_control import (
    AccessConflict,
    AccessDenied,
    AccessNotFound,
)
from knowledge_platform.application.commercial import CommercialError
from knowledge_platform.application.document_rag import DocumentRagService
from knowledge_platform.application.evaluation_control import (
    EvaluationControlError,
    EvaluationErrorCode,
)
from knowledge_platform.delivery.access_control_api import create_access_router
from knowledge_platform.delivery.administration_api import create_administration_router
from knowledge_platform.delivery.auth_api import create_auth_router
from knowledge_platform.delivery.commercial_api import create_commercial_router
from knowledge_platform.delivery.conversation_api import create_conversation_router
from knowledge_platform.delivery.evaluation_api import create_evaluation_router
from knowledge_platform.delivery.identity_provisioning_api import (
    create_identity_provisioning_router,
)
from knowledge_platform.delivery.product_api import create_management_router
from knowledge_platform.delivery.provider_configuration_api import (
    create_provider_configuration_router,
)
from knowledge_platform.delivery.provider_usage_api import create_provider_usage_router
from knowledge_platform.delivery.security import ControlPlaneSecurityMiddleware
from knowledge_platform.delivery.system_conversation_api import (
    create_system_conversation_router,
)
from knowledge_platform.infrastructure.vector_search.store import VectorChunk, VectorSearchStore
from knowledge_platform.modules.document_knowledge.ports import EmbeddingVector, GroundedModelAnswer
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


FRONTEND_ROOT = Path(__file__).resolve().parents[3] / "frontend"
FRONTEND_ENTRYPOINT = FRONTEND_ROOT / "index.html"


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
        def generate(
            self,
            *,
            question: str,
            context: str,
            assistant_instructions: str | None = None,
        ) -> GroundedModelAnswer:
            return GroundedModelAnswer(
                answer="Sanaa is a historic city in Yemen.", evidence_ids=("E1",)
            )

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
    application.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_ROOT),
        name="frontend-assets",
    )
    query_service = service or _demo_service()
    if runtime is not None:
        access = runtime.access_control()
        auth = runtime.auth_gateway()
        application.include_router(
            create_management_router(
                runtime.management_services(), access, runtime.administration()
            )
        )
        application.include_router(
            create_management_router(
                runtime.management_services(), access, runtime.administration(), system=True
            )
        )
        application.include_router(create_conversation_router(runtime.management_services()))
        application.include_router(create_evaluation_router(runtime.evaluation_control()))
        application.include_router(create_access_router(access))
        application.include_router(create_access_router(access, system=True))
        application.include_router(create_administration_router(runtime.administration()))
        application.include_router(
            create_administration_router(runtime.administration(), system=True)
        )
        application.include_router(create_commercial_router(runtime.commercial()))
        application.include_router(create_commercial_router(runtime.commercial(), system=True))
        application.include_router(
            create_provider_usage_router(runtime.provider_usage())
        )
        application.include_router(
            create_provider_configuration_router(runtime.provider_configuration())
        )
        application.include_router(
            create_system_conversation_router(runtime.system_conversations())
        )
        application.include_router(
            create_auth_router(auth, access, secure=runtime.settings.session_cookie_secure)
        )
        application.include_router(
            create_identity_provisioning_router(runtime.identity_provisioning())
        )
        application.add_middleware(
            ControlPlaneSecurityMiddleware,
            auth=auth,
            access=access,
            cookie_secure=runtime.settings.session_cookie_secure,
        )

        @application.exception_handler(AccessDenied)
        async def access_denied_handler(_request: object, _error: AccessDenied) -> JSONResponse:
            return JSONResponse({"detail": "permission denied"}, status_code=403)

        @application.exception_handler(AccessNotFound)
        async def access_not_found_handler(_request: object, _error: AccessNotFound) -> JSONResponse:
            return JSONResponse({"detail": "resource not found"}, status_code=404)

        @application.exception_handler(AccessConflict)
        async def access_conflict_handler(_request: object, error: AccessConflict) -> JSONResponse:
            safe_codes = {
                "ENTITLEMENT_LIMIT_REACHED", "ENTITLEMENT_NOT_CONFIGURED",
                "SUBSCRIPTION_INACTIVE", "SECURITY_POLICY_DENIED",
                "INVITATION_EXPIRY_EXCEEDS_POLICY", "INVITATION_INVALID",
                "MEMBERSHIP_ALREADY_EXISTS",
            }
            detail = str(error)
            if detail not in safe_codes:
                detail = "operation conflicts with current access state"
            return JSONResponse({"detail": detail}, status_code=409)

        @application.exception_handler(CommercialError)
        async def commercial_error_handler(_request: object, error: CommercialError) -> JSONResponse:
            return JSONResponse({"detail": str(error)}, status_code=409)

        @application.exception_handler(EvaluationControlError)
        async def evaluation_error_handler(
            _request: object, error: EvaluationControlError
        ) -> JSONResponse:
            status_code = {
                EvaluationErrorCode.SUITE_NOT_FOUND: 404,
                EvaluationErrorCode.RUN_NOT_FOUND: 404,
                EvaluationErrorCode.ASSISTANT_NOT_FOUND: 404,
                EvaluationErrorCode.MODE_UNSUPPORTED: 409,
                EvaluationErrorCode.EXECUTION_FAILED: 502,
            }[error.code]
            payload: dict[str, object] = {"detail": error.code.value}
            if error.run_id is not None:
                payload["run_id"] = str(error.run_id)
            return JSONResponse(payload, status_code=status_code)

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

    def frontend_entrypoint() -> FileResponse:
        return FileResponse(FRONTEND_ENTRYPOINT, media_type="text/html")

    @application.get("/app", include_in_schema=False)
    def workspace_frontend() -> FileResponse:
        return frontend_entrypoint()

    @application.get("/app/{frontend_path:path}", include_in_schema=False)
    def workspace_frontend_deep_link(frontend_path: str) -> FileResponse:
        del frontend_path
        return frontend_entrypoint()

    @application.get("/system", include_in_schema=False)
    def system_frontend() -> FileResponse:
        return frontend_entrypoint()

    @application.get("/system/{frontend_path:path}", include_in_schema=False)
    def system_frontend_deep_link(frontend_path: str) -> FileResponse:
        del frontend_path
        return frontend_entrypoint()

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


PRODUCT_HTML = """<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>المساعد المعرفي</title><style>
:root{--ink:#172033;--muted:#667386;--accent:#176b87;--line:#dbe4ec;--panel:#fff;--bg:#f3f6f8}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif}.shell{max-width:1180px;margin:auto;padding:1rem}.top{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding:1rem 0}.brand h1{margin:0;font-size:1.35rem}.brand p{margin:.25rem 0;color:var(--muted)}.status{color:#26794f;font-size:.9rem}.grid{display:grid;grid-template-columns:290px 1fr;gap:1rem;margin-top:1rem}.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:1.1rem;box-shadow:0 8px 24px #1720330b}.stack{display:grid;gap:.75rem}.section-title{margin:0 0 .7rem;font-size:1.05rem}label{font-weight:650;font-size:.9rem}input,textarea,select{width:100%;padding:.7rem;border:1px solid #bdccd8;border-radius:9px;font:inherit}button{border:0;border-radius:9px;padding:.7rem 1rem;background:var(--accent);color:#fff;font:inherit;font-weight:700;cursor:pointer}button.secondary{background:#e8f0f3;color:var(--accent)}button:disabled{opacity:.55;cursor:wait}.muted{color:var(--muted);font-size:.88rem}.row{display:flex;gap:.5rem;align-items:center}.badge{display:inline-block;border-radius:99px;padding:.2rem .55rem;background:#e8f0f3;color:var(--accent);font-size:.78rem}.list{display:grid;gap:.45rem}.item{padding:.6rem;border:1px solid var(--line);border-radius:9px;cursor:pointer}.item.selected{border-color:var(--accent);background:#f0f8fa}.chat{min-height:260px;display:grid;grid-template-rows:1fr auto;gap:1rem}.messages{display:grid;gap:.6rem;align-content:start}.message{padding:.65rem .8rem;border-radius:10px;background:#f4f7f9}.message.user{background:#e8f0f3}.result{margin-top:.7rem}.evidence{padding:.7rem;border:1px solid var(--line);border-radius:9px;margin-top:.5rem}.tech{direction:ltr;unicode-bidi:plaintext;color:var(--muted);font-size:.8rem;overflow-wrap:anywhere}@media(max-width:780px){.grid{grid-template-columns:1fr}.top{align-items:flex-start;gap:.5rem}}
</style></head><body><div class="shell"><header class="top"><div class="brand"><h1>المساعد المعرفي</h1><p>مساعد قائم على المعرفة والأدلة</p></div><div class="status">● النظام متاح</div></header>
<main class="grid"><aside class="stack"><section class="card stack"><h2 class="section-title">مساحة العمل</h2><label for="workspace">معرّف مساحة العمل</label><input id="workspace" placeholder="UUID" dir="ltr"><div class="row"><button id="loadWorkspace">تحميل</button><button id="newWorkspace" class="secondary">إنشاء</button></div><p id="workspaceState" class="muted" aria-live="polite">اختر مساحة عمل للبدء.</p></section>
<section class="card stack"><h2 class="section-title">المساعد</h2><select id="assistants" aria-label="المساعدون"></select><input id="assistantName" placeholder="اسم المساعد"><input id="assistantInstructions" placeholder="تعليمات المساعد"><button id="createAssistant">إنشاء مساعد</button><p id="assistantState" class="muted" aria-live="polite"></p></section>
<section class="card stack"><h2 class="section-title">مصادر المعرفة</h2><div id="sources" class="list" aria-live="polite"></div><input id="sourceName" placeholder="اسم المصدر"><select id="sourceKind"><option value="document">ملف</option><option value="structured">بيانات منظمة</option></select><button id="registerSource">تسجيل مصدر</button><input id="file" type="file" accept=".txt,.md,.markdown,.json,.docx,.pdf"><button id="upload" class="secondary">رفع الملف</button><button id="process" class="secondary">معالجة / إعادة معالجة</button><p class="muted">إعادة المعالجة تستخدم الملف المحفوظ ولا تتطلب رفعه مرة أخرى.</p><p id="sourceState" class="muted" aria-live="polite"></p></section></aside>
<section class="stack"><section class="card"><h2 class="section-title">نطاق معرفة المساعد</h2><div id="scope" class="list"></div><p id="scopeState" class="muted" aria-live="polite"></p></section><section class="card chat"><div id="messages" class="messages" aria-live="polite"><p class="muted">أنشئ محادثة لطرح سؤال على مصادرك.</p></div><div class="row"><button id="conversation">محادثة جديدة</button><textarea id="question" rows="2" placeholder="اكتب سؤالك هنا…" aria-label="السؤال"></textarea><button id="ask">اسأل المساعد</button></div><div id="result" aria-live="polite"></div></section></section></main></div>
<script>
const $=id=>document.getElementById(id);let wid=localStorage.getItem('workspace_id')||'',aid='',sid='',cid='';$('workspace').value=wid;document.querySelector('.shell').insertAdjacentHTML('beforeend','<section class="card"><h2 class="section-title">التقييم والتشغيل</h2><div id="ops" class="muted" aria-live="polite">جارٍ تحميل الحالة…</div></section>');
async function call(url,opts={}){const r=await fetch(url,opts);if(!r.ok)throw Error('request failed');if(r.status===204)return null;return r.json()}
let availableSources=[];
async function loadScope(){if(!aid){$('scope').textContent='اختر مساعدًا لعرض نطاق المعرفة.';return}try{const attached=await call('/api/workspaces/'+wid+'/assistants/'+aid+'/sources');renderScope(attached)}catch(_){fail('scopeState')}}
function renderScope(attached){const attachedIds=new Set(attached.map(s=>s.id));if(!availableSources.length){$('scope').textContent='لا توجد مصادر معرفة في مساحة العمل.';return}$('scope').replaceChildren(...availableSources.map(s=>{const d=document.createElement('div');d.className='item';const label=document.createElement('span');label.textContent=s.name+' ';d.append(label);const badge=document.createElement('span');badge.className='badge';badge.textContent=s.lifecycle;d.append(badge);const button=document.createElement('button');button.className='secondary';const isAttached=attachedIds.has(s.id);button.textContent=isAttached?'إزالة من نطاق المساعد':'إضافة إلى نطاق المساعد';button.onclick=async()=>{button.disabled=true;try{await call('/api/workspaces/'+wid+'/assistants/'+aid+'/sources/'+s.id,{method:isAttached?'DELETE':'POST'});await loadScope()}catch(_){fail('scopeState')}finally{button.disabled=false}};d.append(button);return d}))}
const existingRenderSources=renderSources;
renderSources=ss=>{availableSources=ss;existingRenderSources(ss);loadScope()};
$('assistants').onchange=()=>{aid=$('assistants').value;loadScope()};
function fail(el){$(el).textContent='تعذر إكمال الطلب حاليًا. حاول مرة أخرى.'}
async function load(){wid=$('workspace').value.trim();if(!wid)return;try{const w=await call('/api/workspaces/'+wid);localStorage.setItem('workspace_id',wid);$('workspaceState').textContent='مساحة العمل: '+w.name;const as=await call('/api/workspaces/'+wid+'/assistants');$('assistants').replaceChildren(...as.map(a=>{const o=document.createElement('option');o.value=a.id;o.textContent=a.name;return o}));aid=as[0]?.id||'';const ss=await call('/api/workspaces/'+wid+'/sources');renderSources(ss)}catch(_){fail('workspaceState')}}
function renderSources(ss){$('sources').replaceChildren(...ss.map(s=>{const d=document.createElement('div');d.className='item';d.textContent=s.name+' ';const b=document.createElement('span');b.className='badge';b.textContent=s.lifecycle;d.append(b);d.onclick=()=>{sid=s.id;document.querySelectorAll('.item').forEach(x=>x.classList.remove('selected'));d.classList.add('selected')};return d}))}
$('loadWorkspace').onclick=load;$('newWorkspace').onclick=async()=>{try{const w=await call('/api/workspaces',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({name:'مساحة جديدة'})});$('workspace').value=w.id;await load()}catch(_){fail('workspaceState')}};
$('createAssistant').onclick=async()=>{if(!wid)return;try{const a=await call('/api/workspaces/'+wid+'/assistants',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({name:$('assistantName').value||'مساعد جديد',description:null,instructions:$('assistantInstructions').value||'أجب اعتمادًا على الأدلة.',language:'ar',provider:'configured',model_reference:'configured'})});aid=a.id;await load()}catch(_){fail('assistantState')}};
$('registerSource').onclick=async()=>{try{await call('/api/workspaces/'+wid+'/sources',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({name:$('sourceName').value||'مصدر جديد',kind:$('sourceKind').value})});await load()}catch(_){fail('sourceState')}};
$('upload').onclick=async()=>{const f=$('file').files[0];if(!f||!sid)return;try{await call('/api/workspaces/'+wid+'/sources/'+sid+'/upload',{method:'POST',headers:{'content-type':f.type||'application/octet-stream','x-file-name':f.name},body:f});$('sourceState').textContent='تم حفظ الملف الأصلي.';await load()}catch(_){fail('sourceState')}};
$('process').onclick=async()=>{if(!sid)return;try{await call('/api/workspaces/'+wid+'/sources/'+sid+'/process',{method:'POST'});$('sourceState').textContent='اكتملت المعالجة.';await load()}catch(_){fail('sourceState')}};
$('conversation').onclick=async()=>{if(!wid||!aid)return;try{const c=await call('/api/workspaces/'+wid+'/assistants/'+aid+'/conversations',{method:'POST'});cid=c.id;$('messages').replaceChildren();}catch(_){fail('result')}};
$('ask').onclick=async()=>{if(!cid||!$('question').value.trim())return;$('ask').disabled=true;try{const o=await call('/api/workspaces/'+wid+'/conversations/'+cid+'/ask',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({question:$('question').value})});const r=$('result');r.replaceChildren();const h=document.createElement('h3');h.textContent=o.outcome;r.append(h);if(o.answer){const p=document.createElement('p');p.dir='auto';p.textContent=o.answer;r.append(p)}(o.evidence||[]).forEach(e=>{const d=document.createElement('div');d.className='evidence';const p=document.createElement('p');p.dir='auto';p.textContent=e.content;const m=document.createElement('div');m.className='tech';m.dir='ltr';m.textContent=e.provenance_locator+' · '+e.source_id;d.append(p,m);r.append(d)});if(o.outcome!=='GroundedAnswer'&&!o.answer){const p=document.createElement('p');p.textContent=o.outcome==='PolicyDenied'?'تعذر استخدام المحتوى بسبب سياسة مشاركة البيانات.':o.outcome==='InsufficientEvidence'?'لا توجد أدلة كافية في المصادر المرتبطة.':'تعذر إكمال الطلب حاليًا. حاول مرة أخرى.';r.append(p)}}catch(_){fail('result')}finally{$('ask').disabled=false}};
async function loadOps(){try{const h=await call('/health'),r=await call('/ready'),s=await call('/api/evaluation/suites');$('ops').textContent='Health: '+h.status+' · Ready: '+r.status+' · Suites: '+s.length}catch(_){$('ops').textContent='تعذر تحميل حالة التشغيل.'}}
if(wid)load();loadOps();
</script></body></html>"""
