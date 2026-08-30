"""
Constructor de Block Kit para el App Home de Slack.

Es una función pura: recibe datos de dominio y devuelve el JSON de blocks
que espera la API de Slack (`views.publish`). No llama a Slack ni a
Salesforce directamente — de eso se encarga el archivo de wiring
(el punto de entrada de la app, que armamos más adelante).
"""

from domain.case import Case, CaseStatus

# Labels de presentación para Slack — a propósito separados del mapeo
# hacia Salesforce que vive en infrastructure/case_repository.py. Uno es
# "cómo se ve en Slack", el otro "cómo se guarda en Salesforce"; no tienen
# por qué coincidir ni evolucionar juntos.
_STATUS_LABELS: dict[CaseStatus, str] = {
    CaseStatus.NEW: "🆕 Nuevo",
    CaseStatus.ASSIGNED_TO_BRANCH: "🏢 Asignado a sucursal",
    CaseStatus.IN_PROGRESS: "⚙️ En progreso",
    CaseStatus.ESCALATED_INTERNAL: "🔺 Derivado a equipo interno",
    CaseStatus.RETURNED_TO_CALL_CENTER: "↩️ Devuelto a Call Center",
    CaseStatus.CLOSED: "✅ Cerrado",
}


def build_home_view(branch: str, cases: list[Case]) -> dict:
    """Arma el payload de `views.publish` para el App Home de una sucursal."""
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📋 Casos — {branch}", "emoji": True},
        },
        {"type": "divider"},
    ]

    if not cases:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "_No hay casos asignados a esta sucursal por ahora._"},
            }
        )
    else:
        for case in cases:
            status_label = _STATUS_LABELS.get(case.status, case.status.value)
            team_line = f"\n👥 Equipo: {case.assigned_team}" if case.assigned_team else ""
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*#{case.case_number}* — {case.subject}\n"
                            f"🏢 {case.branch} · {status_label}{team_line}"
                        ),
                    },
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Ver detalle", "emoji": True},
                        "action_id": "view_case_detail",
                        "value": case.id,
                    },
                }
            )
            blocks.append({"type": "divider"})

    return {"type": "home", "blocks": blocks}