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


def build_home_view(branch: str, cases: list[Case], selected_status: CaseStatus | None = None) -> dict:
    """Arma el payload de `views.publish` para el App Home de una sucursal."""
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📋 Casos — {branch}", "emoji": True},
        },
        {
            "type": "actions",
            "block_id": "filter_block",
            "elements": _build_filter_buttons(selected_status),
        },
        {
            "type": "actions",
            "block_id": "refresh_block",
            "elements": [_build_refresh_button()],
        },
        {"type": "divider"},
    ]

    if not cases:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "_No hay casos para mostrar con este filtro._"},
            }
        )
    else:
        for case in cases:
            status_label = _STATUS_LABELS.get(case.status, case.status.value)
            team_line = f"\n👥 Equipo: {case.assigned_team}" if case.assigned_team else ""
            channel_line = f"\n💬 <#{case.channel}>" if case.channel else ""
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*#{case.case_number}* — {case.subject}\n"
                            f"🏢 {case.branch} · {status_label}{team_line}{channel_line}"
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


def _build_filter_buttons(selected_status: CaseStatus | None) -> list[dict]:
    """
    Arma la fila de botones de filtro por estado — uno por estado + "Todos".
    El que está activo queda resaltado (style="primary"), los demás neutros.
    """
    options = [("all", "Todos los estados")]
    for status in CaseStatus:
        options.append((status.value, _STATUS_LABELS[status]))

    selected_value = selected_status.value if selected_status is not None else "all"

    buttons = []
    for value, label in options:
        button: dict = {
            "type": "button",
            "action_id": "filter_status_button",
            "text": {"type": "plain_text", "text": label, "emoji": True},
            "value": value,
        }
        if value == selected_value:
            button["style"] = "primary"
        buttons.append(button)
    return buttons


def format_status_label(status: CaseStatus) -> str:
    """Label de presentación (con emoji) para un estado — reutilizable fuera de este módulo."""
    return _STATUS_LABELS.get(status, status.value)


def _build_refresh_button() -> dict:
    """Botón para volver a consultar Salesforce y republicar el Home al toque."""
    return {
        "type": "button",
        "action_id": "refresh_home",
        "text": {"type": "plain_text", "text": "🔄 Actualizar", "emoji": True},
    }