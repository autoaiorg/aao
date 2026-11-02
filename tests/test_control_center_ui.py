import re
from pathlib import Path

from fastapi.testclient import TestClient

from aao.work_management_api import app


def control_center_source() -> str:
    frontend = Path(__file__).parents[1] / "frontend"
    return "\n".join(
        (frontend / name).read_text()
        for name in ("index.html", "control-center.css", "control-center.js")
    )


def test_control_center_served_at_root():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert '<html lang="es">' in response.text
    assert "AAO Control Center" in response.text
    # The API serves the current Vite app when its build exists, and the legacy
    # static page as a fallback in environments that do not build the app.
    assert "<title>AAO Control Center" in response.text
    assert 'id="root"' in response.text or "Consola de Operaciones Organizativas" in response.text


def test_control_center_navigation_and_views_present():
    html = control_center_source()

    # Navigation tabs
    assert 'role="tablist"' in html
    assert 'data-tab="tab-kanban"' in html
    assert 'data-tab="tab-tasks"' in html
    assert 'data-tab="tab-agents"' in html
    assert 'data-tab="tab-capabilities"' in html
    assert 'data-tab="tab-proposals"' in html
    assert 'data-tab="tab-executions"' in html
    assert 'data-tab="tab-evidence"' in html

    # Tab panels
    assert 'id="tab-kanban"' in html
    assert 'id="tab-tasks"' in html
    assert 'id="tab-agents"' in html
    assert 'id="tab-capabilities"' in html
    assert 'id="tab-proposals"' in html
    assert 'id="tab-executions"' in html
    assert 'id="tab-evidence"' in html


def test_control_center_kanban_six_lifecycle_states():
    html = control_center_source()
    assert 'id="board"' in html
    assert 'const states = ["INBOX", "READY", "IN_PROGRESS", "IN_REVIEW", "VERIFIED", "DONE"];' in html
    assert 'INBOX: "Entrada"' in html
    assert 'READY: "Preparado"' in html
    assert 'IN_PROGRESS: "En curso"' in html
    assert 'IN_REVIEW: "Revisión"' in html
    assert 'VERIFIED: "Verificado"' in html
    assert 'DONE: "Completado"' in html


def test_control_center_agents_and_identity_management():
    html = control_center_source()
    assert '"/v1/principals/me"' in html
    assert 'id="agents-table-body"' in html
    assert 'id="session-badge"' in html
    assert 'id="session-agent-id"' in html
    assert 'Identidad y Principales del Proyecto' in html
    assert 'Sesión Actual' in html


def test_control_center_skills_and_capabilities_as_first_class_citizens():
    html = control_center_source()
    assert 'id="capabilities"' in html
    assert 'id="filter-cap-type"' in html
    assert 'value="agent_skill">Habilidades de Agente (Skills)<' in html
    assert 'Habilidad (Skill)' in html
    assert 'capability.capability_type === "agent_skill"' in html
    assert '"Ejecución autorizada: no"' in html
    assert 'capability.execution_authorized' not in html
    assert '"Riesgos y límites: "' in html
    assert '"Pruebas y evidencia: "' in html
    assert '"Procedencia: "+JSON.stringify(capability.provenance)' in html


def test_control_center_code_proposals_transparency():
    html = control_center_source()
    assert 'id="proposals-table-body"' in html
    assert 'Propuestas de Código (Patch Proposals)' in html
    assert 'p.base_sha' in html
    assert 'p.patch_sha256' in html
    assert 'p.changed_paths' in html
    assert 'p.validations' in html
    assert 'v.candidate_tree' in html
    assert 'No disponible (aislado)' in html


def test_control_center_executions_and_logs():
    html = control_center_source()
    assert 'id="executions-table-body"' in html
    assert 'Ejecuciones Técnicas (Execution Queue)' in html
    assert 'e.worker_id' in html
    assert 'res.candidate_sha' in html
    assert 'res.stdout' in html
    assert 'res.stderr' in html


def test_control_center_audits_and_evidence():
    html = control_center_source()
    assert 'id="evidence-table-body"' in html
    assert 'Evidencias de Integridad y Dictámenes de Auditoría' in html
    assert 'rev.reviewer_id' in html
    assert 'rev.decision' in html
    assert 'rev.sha_bound' in html
    assert 'rev.candidate_sha' in html


def test_control_center_ephemeral_security_controls():
    html = control_center_source()
    # Memory-only token
    assert 'let readerToken = null;' in html
    assert 'function clearReaderSession()' in html
    assert 'id="disconnect"' in html
    assert 'headers:{"X-Agent-Token":readerToken}' in html
    assert '"X-CEO-Token"' not in html
    assert 'localStorage' not in html
    assert 'sessionStorage' not in html


def test_control_center_task_detail_modal_inspector():
    html = control_center_source()
    assert 'id="drawer-overlay"' in html
    assert 'id="drawer-acceptance-criteria"' in html
    assert 'id="drawer-evidence-list"' in html
    assert 'id="drawer-executions-list"' in html
    assert 'id="drawer-reviews-list"' in html
    assert 'id="drawer-proposals-list"' in html
    assert 'aria-modal="true"' in html
    assert 'role="dialog"' in html


def test_control_center_authentication_and_revocation_behavior():
    html = control_center_source()
    # 401 / 403 error handling immediately purges reader session
    assert "if (r.status === 401 || r.status === 403)" in html
    assert "clearReaderSession();" in html
    assert "Credencial rechazada o revocada por el núcleo local" in html
    # Disconnect clears credentials and state
    assert 'disconnectBtn.addEventListener("click"' in html
    assert "readerToken = null;" in html
    assert "currentPrincipal = null;" in html


def test_control_center_loading_and_error_states():
    html = control_center_source()
    assert "Cargando datos reales de PostgreSQL…" in html
    assert "No se pudo cargar el tablero: " in html
    assert "Sin proyectos autorizados para esta identidad" in html
    assert "Sin tareas" in html
    assert "No hay tareas registradas para este filtro." in html
    assert "No hay capacidades registradas para este proyecto." in html
    assert "No hay propuestas de código registradas en este proyecto." in html
    assert "No hay ejecuciones registradas en este proyecto." in html
    assert "No hay evidencias ni revisiones registradas en este proyecto." in html


def test_control_center_tab_navigation_logic():
    html = control_center_source()
    assert 'tab.addEventListener("click"' in html
    assert 't.classList.remove("active");' in html
    assert 't.setAttribute("aria-selected", "false");' in html
    assert 'tab.classList.add("active");' in html
    assert 'tab.setAttribute("aria-selected", "true");' in html


def test_control_center_governance_strictly_separates_evaluations_from_executions():
    html = control_center_source()
    # Capabilities and evaluations must never be represented as executions
    assert 'card.append(node("div", "Ejecución autorizada: no", "meta-line disclaimer"));' in html
    assert 'card.append(node("div", "Registro sin permiso de ejecución implícito", "meta-line"));' in html
    assert 'card.append(node("div", "Evaluación no autoriza ejecución.", "meta-line disclaimer"));' in html
    assert "capability.execution_authorized" not in html


def test_control_center_governance_strictly_avoids_claiming_independent_audit():
    html = control_center_source()
    # Safety note warns that records are not certified independent audits
    assert "Los dictámenes de auditoría son registros almacenados y no sustituyen una certificación de auditoría independiente." in html
    assert "Registro almacenado; independencia y validez no certificadas." in html


def test_control_center_governance_does_not_treat_in_review_tasks_as_approved():
    html = control_center_source()
    # IN_REVIEW status is mapped to "Revisión", never "Aprobado"
    assert 'IN_REVIEW: "Revisión"' in html
    # Approval reviews are noted as stored auditor reviews, not task completion or certified state
    assert 'else if (rev.decision === "APPROVE") meta.append(node("span", "Aprobación registrada", "pill approve"));' in html
    assert 'rev.decision === "APPROVE" ? "Aprobación registrada"' in html


def test_patch_proposal_diff_inspection_requires_auditor_token():
    with TestClient(app) as client:
        # Calls with X-Agent-Token (or missing auditor token) must be rejected with 403
        response = client.get(
            "/v1/work/work-sample/patch-proposals/proposal-sample",
            headers={"X-Agent-Token": "sample-agent-token"},
        )
        assert response.status_code == 403
        assert "Individual auditor credential rejected" in response.json()["detail"]


def test_control_center_git_lifecycle_tab_and_views_present():
    html = control_center_source()
    assert 'data-tab="tab-git-lifecycle"' in html
    assert 'Ciclo Git e Integración' in html
    assert 'id="tab-git-lifecycle"' in html
    assert 'Ciclo de Integración Git Local y Control de Promoción' in html


def test_control_center_git_lifecycle_tables_and_exact_shas_present():
    html = control_center_source()
    assert 'id="git-candidates-table-body"' in html
    assert 'id="git-reviews-table-body"' in html
    assert 'id="git-promotion-history-table-body"' in html
    assert 'sha-mono' in html
    assert 'baseSha' in html or 'base_sha' in html
    assert 'patchSha256' in html or 'patch_sha256' in html
    assert 'candidate_tree' in html
    assert 'candidate_sha' in html


def test_control_center_promotion_gate_strictly_fails_closed():
    html = control_center_source()
    # Promotion button is permanently disabled in the DOM without verifiable authority
    assert 'id="btn-promote-candidate" class="primary" disabled aria-disabled="true"' in html
    assert 'PROMOCIÓN BLOQUEADA' in html
    # Explicit fail-closed reasoning and governance limits
    assert "Controlador no autorizado" in html
    assert "Falta de Autoridad de Promoción" in html
    assert "Falta de Certificación de Auditoría Independiente" in html
    assert "La interfaz no permite promover candidatos mientras el controlador local no disponga de autorización verificable" in html
    assert "Constitución arts. 3 y 6" in html


def test_control_center_git_lifecycle_veto_and_unaccredited_promotions():
    html = control_center_source()
    # VETO triggers immediate veto status and blocks promotion
    assert 'r.decision === "VETO"' in html
    assert 'VETO ACTIVO' in html
    assert 'INTEGRACIÓN PROHIBIDA' in html

    # Historical checks are faithfully displayed without fabricated base SHAs
    assert "Check Histórico" in html
    assert "No aplica" in html
    assert "Histórico · No acreditado para integración" in html

    # Zero accredited promotions in repository
    assert "Cero Promociones Acreditadas" in html
    assert "No existen promociones acreditadas ni ejecutadas en el repositorio canónico" in html

    # Unaccredited development branches explicitly separated in Table 4
    assert 'id="git-unaccredited-candidates-table-body"' in html
    assert "NO ACREDITADA (Gate cerrado)" in html
    assert "142d6c5c542e6b6f790175f7a8cf14c23c6be73b" in html
    assert "91eb7543658fe92875cefa3de1e27704d830feb7" in html
    assert "ea549700ad82405dd0f64eb9121aa116d281a022" in html


def test_control_center_assets_are_separate_same_origin_resources():
    with TestClient(app) as client:
        page = client.get("/")
        script_path = re.search(r'<script[^>]+src="([^"]+)"', page.text)
        stylesheet_path = re.search(r'<link[^>]+href="([^"]+\.css)"', page.text)
        assert script_path and stylesheet_path
        script_url = "/" + script_path.group(1).removeprefix("./").lstrip("/")
        stylesheet_url = "/" + stylesheet_path.group(1).removeprefix("./").lstrip("/")
        stylesheet = client.get(stylesheet_url)
        script = client.get(script_url)

    assert page.status_code == stylesheet.status_code == script.status_code == 200
    assert "text/css" in stylesheet.headers["content-type"]
    assert "javascript" in script.headers["content-type"]
    assert "<style" not in page.text
    assert "<script>" not in page.text


def test_control_center_markup_has_no_inline_style_attributes():
    html = (Path(__file__).parents[1] / "frontend" / "index.html").read_text()
    assert "style=" not in html
    assert html.count("<html") == html.count("</html>") == 1
    assert html.count("<body") == html.count("</body>") == 1
