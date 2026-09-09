"""Operational contracts for the Stage 6I SaaS shell."""

from collections.abc import Callable
import json
import shutil
import subprocess
from typing import cast

import pytest

from knowledge_platform.delivery.app import create_app


def _page(path: str = "/app") -> str:
    route = next(item for item in create_app().routes if getattr(item, "path", None) == path)
    return cast(Callable[..., str], route.endpoint)()


def test_routes_and_structural_rtl_shell_remain_available() -> None:
    application = create_app()
    paths = {getattr(route, "path", None) for route in application.routes}
    page = _page()

    assert {"/app", "/app/{product_path:path}", "/app/acceptance"} <= paths
    assert '<html lang="ar" dir="rtl">' in page
    assert ".shell{min-height:100vh;display:grid;grid-template-columns:minmax(0,1fr) 218px;direction:ltr}" in page
    assert ".sidebar{grid-column:2;grid-row:1;direction:rtl" in page
    assert ".main{grid-column:1;grid-row:1;direction:rtl" in page
    for route in ("assistants", "knowledge", "conversations", "evaluation", "operations", "settings"):
        assert f'href="/app/{route}"' in page


def test_workspace_catalog_creation_and_switching_scope_all_state() -> None:
    page = _page()

    assert "workspace_catalog" in page
    assert "async function loadCatalog()" in page
    assert "async function selectWorkspace(id)" in page
    assert "saveWorkspaceCache();state.workspaceId=id;restoreWorkspaceCache(id)" in page
    assert "await loadCore();await renderRoute()" in page
    assert "'/api/workspaces'" in page
    assert "إنشاء واختيار المساحة" in page
    assert "Workspace UUID" not in page
    assert "معرّف مساحة العمل" not in page


def test_assistant_create_edit_open_scope_and_conversation_operations() -> None:
    page = _page()

    assert "method:id?'PATCH':'POST'" in page
    assert "تعليمات المساعد" in page
    assert "'/assistants/'+a.id+'/sources'" in page
    assert "ربط مصدر معرفة" in page
    assert "method:'DELETE'" in page
    assert "سيتم فصل المصدر عن هذا المساعد فقط وسيبقى المصدر محفوظًا في مساحة العمل" in page
    assert "'/assistants/'+aid+'/conversations'" in page
    assert "startButton(a.id)" in page
    assert "حذف المصدر" not in page


def test_assistant_workspace_has_real_deep_linked_local_navigation() -> None:
    page = _page()

    assert "function assistantHref(id,section='')" in page
    assert "function assistantTabs(a,current)" in page
    assert "['overview','نظرة عامة','']" in page
    assert "['knowledge','المعرفة','knowledge']" in page
    assert "['instructions','التعليمات','instructions']" in page
    assert "['conversations','المحادثات','conversations']" in page
    assert "assistantMatch=p.match(/^\\/app\\/assistants\\/([^/]+)" in page
    assert "renderAssistant(assistantMatch[1],assistantMatch[2]||'overview',generation)" in page
    assert "المساعدون / '+a.name+' / '+names[current]" in page
    assert "معرّف المساعد" not in page


def test_assistant_overview_uses_real_knowledge_and_conversation_data() -> None:
    page = _page()

    assert "linked.filter(s=>s.lifecycle==='ready').length" in page
    assert "المصادر المرتبطة" in page
    assert "المصادر الجاهزة" in page
    assert "لا توجد مصادر جاهزة للاستخدام بعد" in page
    assert "لا توجد مصادر معرفة مرتبطة بهذا المساعد" in page
    assert "conversations.slice(0,5)" in page
    assert "تعذر تحميل محادثات هذا المساعد" in page
    assert "لم تبدأ محادثة مع هذا المساعد بعد" in page


def test_assistant_knowledge_is_association_only_and_state_aware() -> None:
    page = _page()

    assert "function renderAssistantKnowledge(a,linked)" in page
    assert "renderAssistantKnowledge(a,linked)" in page
    assert "state.sources.filter(s=>!ids.has(s.id))" in page
    assert "جميع مصادر مساحة العمل مرتبطة بهذا المساعد" in page
    assert "سيتم فصل المصدر عن هذا المساعد فقط وسيبقى المصدر محفوظًا في مساحة العمل" in page
    assert "method:'DELETE'" in page
    assert "فتح المصدر" in page
    assert "open.href='/app/knowledge'" in page
    assert "حذف المصدر" not in page


def test_instruction_editor_is_dirty_checked_and_preserves_hidden_configuration() -> None:
    page = _page()

    assert "function renderAssistantInstructions(a)" in page
    assert "save.disabled=true" in page
    assert "textarea.value.trim()===initial.trim()" in page
    assert "if(!instructions||instructions===initial.trim())return" in page
    assert "method:'PATCH'" in page
    assert "name:a.name,description:a.description,instructions,language:a.language" in page
    assert "provider:a.provider,model_reference:a.model_reference" in page
    assert "تحدد هذه التعليمات أسلوب المساعد وسلوكه داخل حدود مصادر المعرفة" in page
    assert "تم حفظ التغييرات" in page
    assert "تعذر حفظ التعليمات" in page


def test_assistant_conversations_use_server_side_assistant_filter_and_binding() -> None:
    page = _page()

    assert "'?assistant_id='+encodeURIComponent(assistantId)" in page
    assert "function renderAssistantConversations(a,items,error)" in page
    assert "startButton(a.id)" in page
    assert "navigate('/app/conversations/'+item.id)" in page
    assert "'/assistants/'+aid+'/conversations'" in page
    assert "if(!value)return'محادثة سابقة'" in page


def test_assistant_artifact_format_is_real_normalized_and_bounded() -> None:
    page = _page()

    assert "function artifactSuffix(artifact)" in page
    assert "artifact.suffix||''" in page
    assert "extension(artifact.original_filename||'')" in page
    assert "formatLabels[normalized]?normalized:''" in page
    assert "suffix?formatLabels[suffix]:'غير متاح'" in page
    assert "start+=4" in page
    assert "await refreshArtifactMetadata(linked)" in page
    assert "structured does not imply" not in page


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_artifact_format_and_rtl_date_contracts_execute_in_node() -> None:
    page = _page()
    artifact_start = page.index("function artifactSuffix(artifact)")
    artifact_code = page[artifact_start:page.index("async function refreshArtifactMetadata", artifact_start)]
    date_start = page.index("function assistantDate(value)")
    date_code = page[date_start:page.index("function assistantConversationTable", date_start)]
    program = """
const formatLabels={'.pdf':'PDF','.docx':'DOCX','.txt':'TXT','.md':'Markdown','.markdown':'Markdown','.json':'JSON'};
const state={artifacts:new Map()};
function extension(name){const i=name.lastIndexOf('.');return i<0?'':name.slice(i).toLowerCase()}
""" + artifact_code + date_code + """
state.artifacts.set('document-json',{artifact_present:true,suffix:'json',original_filename:'source.json'});
state.artifacts.set('structured-pdf',{artifact_present:true,suffix:'',original_filename:'source.pdf'});
state.artifacts.set('unknown',{artifact_present:true,suffix:'bin',original_filename:'source.bin'});
console.log(JSON.stringify([
 artifactFormat({id:'document-json',kind:'document'}),
 artifactFormat({id:'structured-pdf',kind:'structured'}),
 artifactFormat({id:'unknown',kind:'document'}),
 assistantDate('2026-09-03T10:30:00+00:00'),
 assistantDate(null)
]));
"""

    completed = subprocess.run(
        [shutil.which("node") or "node", "-e", program],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert json.loads(completed.stdout) == [
        "JSON", "PDF", "غير متاح", "03/09/2026", "محادثة سابقة"
    ]


def test_assistant_tabs_use_history_navigation_and_restore_popstate() -> None:
    page = _page()

    assert "async function navigate(url,{replace=false}={})" in page
    assert "history.pushState({},'',target.pathname+target.search)" in page
    assert "function eligibleInternalLink(event,link)" in page
    assert "event.preventDefault();navigate(link.href)" in page
    assert "window.addEventListener('popstate'" in page
    assert "await renderRoute()" in page
    assert "routeGeneration:0" in page
    assert "const generation=++state.routeGeneration" in page
    assert "token!==state.routeGeneration" in page
    assert "جارٍ تحميل القسم" not in page
    assert "assistantMatch=p.match" in page


def test_assistant_route_loading_always_has_safe_completion_contract() -> None:
    page = _page()

    assert "function readArtifactMetadata(source,owner)" in page
    assert "new AbortController()" in page
    assert "controller.abort(),6000" in page
    assert "finally{clearTimeout(timeout)}" in page
    assert "Promise.allSettled(batch.map(source=>readArtifactMetadata(source,owner)))" in page
    assert "start+=4" in page
    assert "token!==state.routeGeneration" in page
    assert "تعذر تحميل مصادر معرفة المساعد" in page
    assert "إعادة المحاولة" in page


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_artifact_loader_settles_success_failure_and_pending_requests() -> None:
    page = _page()
    start = page.index("async function readArtifactMetadata(source,owner)")
    code = page[start:page.index("function sourceActions", start)].replace("6000", "20", 1)
    program = """
const state={workspaceId:'workspace',artifacts:new Map()};
let active=0,maxActive=0;
async function api(path,options={}) {
  active++; maxActive=Math.max(maxActive,active);
  const id=path.split('/').at(-2);
  try {
    if(id==='failed') throw Error('failed');
    if(id==='pending') return await new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Error('aborted'))));
    await new Promise(resolve=>setTimeout(resolve,2));
    return {artifact_present:true,suffix:id==='json'?'.json':'.txt'};
  } finally { active--; }
}
""" + code + """
(async()=>{
 await refreshArtifactMetadata(['json','failed','pending','a','b'].map(id=>({id})));
 console.log(JSON.stringify({size:state.artifacts.size,maxActive,pending:state.artifacts.get('pending'),failed:state.artifacts.get('failed')}));
})().catch(()=>process.exit(2));
"""

    completed = subprocess.run(
        [shutil.which("node") or "node", "-e", program],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)

    assert result["size"] == 5
    assert result["maxActive"] <= 4
    assert result["pending"] == {"artifact_present": False}
    assert result["failed"] == {"artifact_present": False}


def test_assistant_header_and_instruction_editor_are_compact() -> None:
    page = _page()

    assert "setTitle(names[current],'المساعدون / '+a.name+' / '+names[current])" in page
    assert ".instruction-editor{max-width:820px}" in page
    assert ".instruction-editor textarea{min-height:112px;height:112px" in page
    assert "instruction-actions" in page
    assert "button secondary small','إلغاء'" in page
    assert "button small','حفظ التغييرات'" in page
    assert "cancel.disabled=save.disabled" not in page
    assert "save.disabled=cancel.disabled=clean" in page


def test_system_wide_router_intercepts_only_eligible_app_links() -> None:
    page = _page()

    assert "function eligibleInternalLink(event,link)" in page
    assert "event.button!==0" in page
    assert "event.ctrlKey||event.metaKey||event.shiftKey||event.altKey" in page
    assert "link.target==='_blank'" in page
    assert "link.hasAttribute('download')" in page
    assert "target.origin===location.origin" in page
    assert "target.pathname.startsWith('/app')" in page
    assert "!target.pathname.startsWith('/app/acceptance')" in page
    assert "document.addEventListener('click'" in page
    assert "location.reload(" not in page
    assert "location.href=" not in page


def test_spa_cache_and_workspace_switching_are_explicitly_scoped() -> None:
    page = _page()

    assert "workspaceCache:new Map()" in page
    assert "assistantDetails:new Map()" in page
    assert "assistantSources:new Map()" in page
    assert "conversationLists:new Map()" in page
    assert "conversationDetails:new Map()" in page
    assert "function saveWorkspaceCache()" in page
    assert "function restoreWorkspaceCache(id)" in page
    assert "history.replaceState" in page
    assert "current.startsWith('/app/assistants')?'/app/assistants':'/app/conversations'" in page
    assert "state.assistantSources.delete(a.id)" in page
    assert "state.conversationLists.clear()" in page


def test_assistant_shell_is_persistent_and_sections_use_cached_content() -> None:
    page = _page()

    assert "function mountAssistantShell(a,linked,current)" in page
    assert "root.dataset.assistant!==a.id||!host" in page
    assert "host.id='assistantSection'" in page
    assert "function renderCachedAssistantSection" in page
    assert "state.assistantDetails.get(id)" in page
    assert "state.assistantSources.get(id)" in page
    assert "state.conversationLists.get(conversationKey)" in page
    assert "جارٍ تحميل القسم" not in page


def test_evaluation_exposes_only_real_catalog_metadata() -> None:
    page = _page()

    assert "api('/api/evaluation/suites')" in page
    assert "['المعرّف','المجموعة','الإصدار','عدد الحالات']" in page
    assert "s.key" in page
    assert "s.name" in page
    assert "s.version" in page
    assert "s.case_count" in page
    assert "تشغيل التقييم" not in page
    assert "نسبة النجاح" not in page
    assert "s.sha256" not in page


def test_operations_are_cached_refreshable_and_productized() -> None:
    page = _page()

    assert "Promise.allSettled([api('/health'),api('/ready')])" in page
    assert "state.operations" in page
    assert "action('تحديث',()=>renderOperations(++state.routeGeneration)" in page
    for raw, label in (("ok", "سليم"), ("ready", "جاهز"), ("production", "وضع الإنتاج"), ("demo", "وضع تجريبي")):
        assert f"{raw}:'{label}'" in page
    for secret in ("database host", "provider uptime", "token usage"):
        assert secret not in page.lower()


def test_route_loading_is_local_and_all_async_routes_are_generation_owned() -> None:
    page = _page()

    assert "class=\"component-loading\"" in page
    assert "function localLoading" in page
    assert "generation===state.routeGeneration" in page
    assert "Promise.allSettled(batch.map(source=>readArtifactMetadata(source,owner)))" in page
    assert "جارٍ تحميل القسم" not in page
    assert "replaceChildren(el('div','loading'" not in page


def test_source_kind_and_physical_format_are_separate_and_validated() -> None:
    page = _page()

    assert '<option value="document">مستند</option>' in page
    assert '<option value="structured">بيانات منظمة</option>' in page
    assert 'accept=".pdf,.docx,.txt,.md,.markdown,.json"' in page
    for suffix, label in ((".pdf", "PDF"), (".docx", "DOCX"), (".txt", "TXT"), (".md", "Markdown"), (".json", "JSON")):
        assert f"'{suffix}':'{label}'" in page
    assert "format.textContent='صيغة الملف: '+formatLabels[suffix]" in page
    assert "صيغة غير مدعومة" in page
    assert "if(!formatLabels[suffix])" in page
    assert "نوع المصدر يصف استخدام المعرفة" in page


def test_source_artifact_and_lifecycle_actions_are_state_aware() -> None:
    page = _page()

    assert "'/artifact'" in page
    assert "artifact_present" in page
    assert "s.lifecycle==='registered'||s.lifecycle==='failed'" in page
    assert "s.lifecycle!=='preparing'&&a.artifact_present" in page
    assert "s.lifecycle==='ready'?'إعادة المعالجة':'معالجة المصدر'" in page
    assert "تستخدم إعادة المعالجة الملف المحفوظ ولا تحتاج إلى رفعه مرة أخرى" in page
    assert "تم حفظ الملف الأصلي" in page


def test_conversation_flow_and_typed_outcomes_are_productized() -> None:
    page = _page()

    assert "fillConversationAssistants" in page
    assert "await navigate('/app/conversations/'+c.id)" in page
    assert "'/conversations/'+id+'/ask'" in page
    assert "send.disabled=input.disabled=true" in page
    assert "form.requestSubmit()" in page
    for internal, label in (
        ("GroundedAnswer", "إجابة موثقة"),
        ("InsufficientEvidence", "الأدلة غير كافية"),
        ("PolicyDenied", "الطلب غير مسموح"),
        ("TechnicalFailure", "تعذر إكمال الطلب"),
    ):
        assert f"{internal}:'{label}'" in page
    assert "assistant.name" in page


def test_grounded_evidence_is_rendered_without_raw_ids_or_paths() -> None:
    page = _page()

    assert "function evidenceChips(items)" in page
    assert "function showEvidence(item,index)" in page
    assert "item.content" in page
    assert "friendlyProvenance(item.provenance_locator)" in page
    assert "source?.name||'مصدر معرفة'" in page
    assert "item.source_id" in page  # used only to resolve the human-readable source name
    assert "textContent=item.source_id" not in page
    for secret in ("PLATFORM_DATABASE_DSN", "OPENROUTER_API_KEY", "Authorization", "document_chunks", "pgvector"):
        assert secret not in page


def test_evidence_presentation_recognizes_qa_paths_and_keeps_safe_fallback() -> None:
    page = _page()

    assert "function parseEvidencePresentation(content)" in page
    assert "marker=/messages[.](\\d+)[.](role|content):\\s*/g" in page
    assert "end=position+1<matches.length?matches[position+1].index:raw.length" in page
    assert "records.size!==2" in page
    assert "Object.keys(record).length!==2" in page
    assert "questions.length!==1||answers.length!==1" in page
    assert "السؤال في المصدر" in page
    assert "الإجابة في المصدر" in page
    assert "else body.append(el('div','inspector-content',item.content))" in page
    assert "friendlyProvenance(item.provenance_locator)" in page


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_evidence_parser_accepts_line_and_flat_shapes_but_rejects_ambiguity() -> None:
    page = _page()
    start = page.index("function parseEvidencePresentation(content)")
    parser = page[start:page.index("function showEvidence", start)]
    fixtures = [
        (
            "messages.0.role: user\nmessages.0.content: السؤال\n"
            "messages.1.role: assistant\nmessages.1.content: الإجابة"
        ),
        (
            "messages.0.role: user messages.0.content: السؤال "
            "messages.1.role: assistant messages.1.content: الإجابة"
        ),
        "messages.0.role: user messages.0.content: السؤال messages.1.content: الإجابة",
    ]
    program = parser + ";console.log(JSON.stringify(" + json.dumps(
        fixtures, ensure_ascii=False
    ) + ".map(parseEvidencePresentation)))"

    completed = subprocess.run(
        [shutil.which("node") or "node", "-e", program],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    parsed = json.loads(completed.stdout)

    assert parsed[0] == {"question": "السؤال", "answer": "الإجابة"}
    assert parsed[1] == {"question": "السؤال", "answer": "الإجابة"}
    assert parsed[2] is None


def test_conversation_preview_uses_typed_outcomes_and_sanitizes_legacy_failures() -> None:
    page = _page()

    assert "function conversationPreview(item)" in page
    assert "item.last_outcome&&item.last_outcome!=='GroundedAnswer'" in page
    assert "document rag failed" in page
    assert "no evidence supports an answer" in page
    assert "conversationPreview(item)" in page


def test_three_pane_conversation_workspace_lists_and_reconstructs_messages() -> None:
    page = _page()

    assert "conversation-workspace" in page
    assert "conversation-nav" in page
    assert "conversation-chat" in page
    assert "evidence-inspector" in page
    assert "api('/api/workspaces/'+owner+'/conversations'" in page
    assert "last_message_preview" in page
    assert "m.outcome?{outcome:m.outcome,evidence:m.evidence||[]}:null" in page
    assert "اختر دليلاً لعرض تفاصيله" in page
    assert "الدليل "+"'" in page
    assert "رسالة سابقة" in page


def test_active_conversation_composer_is_always_rendered_and_viewport_contained() -> None:
    page = _page()

    assert "chat.append(head,messages,form)" in page
    assert "messages.append(el('div','empty'" in page
    assert "grid-template-rows:minmax(0,1fr)" in page
    assert (
        ".conversation-nav,.conversation-chat,.evidence-inspector{direction:rtl;"
        "min-width:0;min-height:0;overflow:hidden}"
    ) in page
    assert ".conversation-rows{min-height:0;overflow-y:auto}" in page
    assert ".conversation-chat .messages{min-height:0;overflow-y:auto}" in page
    assert ".content:has(.conversation-workspace){height:calc(100dvh - 46px)" in page


def test_evidence_chips_activate_inspector_with_source_and_provenance() -> None:
    page = _page()

    assert "chip.onclick=()=>showEvidence(item,index+1)" in page
    assert "source?.name||'مصدر معرفة'" in page
    assert "inspector-content" in page
    assert "الموضع" in page
    assert "item.provenance_locator" in page
    assert "representation" not in page.lower()
    assert "embedding" not in page.lower()


def test_compact_dense_design_tokens_are_present() -> None:
    page = _page()

    assert "font:13px/1.45" in page
    assert "--radius:7px" in page
    assert "grid-template-columns:minmax(0,1fr) 218px" in page
    assert ".topbar{height:46px" in page
    assert ".nav a{display:flex;align-items:center;gap:8px;height:34px" in page
    assert ".button{height:32px" in page
    assert "input,textarea,select{height:34px" in page
    assert "th,td{height:38px;padding:6px 10px" in page
    assert ".panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:12px" in page
    assert "--nav:#20252d" in page


def test_acceptance_surface_is_preserved_and_separate() -> None:
    product = _page()
    acceptance = _page("/app/acceptance")

    assert "workspace-switcher" in product
    assert 'id="loadWorkspace"' not in product
    assert 'id="loadWorkspace"' in acceptance
    assert product != acceptance
