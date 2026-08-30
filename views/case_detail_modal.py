"""
Constructor de Block Kit para el modal de detalle de un caso.

Función pura, igual que views/home.py: recibe un Case y arma el payload
de `views.open` / `views.update`. Las acciones ofrecidas dependen del
estado actual del caso, reflejando las mismas transiciones válidas que
domain/case.py — pero acá es una copia deliberada a nivel de presentación,
no una importación del diccionario privado del dominio. Si en algún
momento se desincroniza, lo peor que pasa es que Slack ofrezca una opción
que domain.Case va a rechazar de todos modos al guardar (ver
application/case_service.py).
"""

from domain.case import Case, CaseStatus

CALLBACK_ID = "case_detail_modal"

# Equipos internos disponibles para derivar (tal cual se cargaron en el
# picklist Internal_Team__c de Salesforce).
_TEAM_OPTIONS = ["Legales", "Logistica", "Marketing", "Cobros"]

# Qué acciones puede disparar la sucursal desde Slack, según el estado
# actual del caso.
_ACTIONS_BY_STATUS: dict[CaseStatus, list[tuple[str, str]]] = {
    CaseStatus.NEW: [],
    CaseStatus.ASSIGNED_TO_BRANCH: [
        ("start_progress", "⚙️ Empezar a trabajar"),
        ("derive_to_internal_team", "🔺 Derivar a equipo interno"),
        ("return_to_call_center", "↩️ Devolver a Call Center"),
    ],
    CaseStatus.IN_PROGRESS: [
        ("derive_to_internal_team", "🔺 Derivar a equipo interno"),
        ("return_to_call_center", "↩️ Devolver a Call Center"),
        ("close_case", "✅ Cerrar caso"),
    ],
    CaseStatus.ESCALATED_INTERNAL: [
        ("start_progress", "⚙️ Volver a en progreso"),
        ("return_to_call_center", "↩️ Devolver a Call Center"),
        ("close_case", "✅ Cerrar caso"),
    ],
    CaseStatus.RETURNED_TO_CALL_CENTER: [],
    CaseStatus.CLOSED: [],
}


def build_case_detail_modal(case: Case) -> dict:
    """Arma el payload de `views.open` / `views.update` para el detalle de un caso."""
    team_line = f"\n*Equipo interno:* {case.assigned_team}" if case.assigned_team else ""
    channel_line = f"\n*Canal:* <#{case.channel}>" if case.channel else "\n*Canal:* _Todavía no se creó_"
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Caso #{case.case_number}*\n"
                    f"*Asunto:* {case.subject}\n"
                    f"*Sucursal:* {case.branch}\n"
                    f"*Estado:* {case.status.value}"
                    f"{team_line}"
                    f"{channel_line}"
                ),
            },
        },
        {"type": "divider"},
    ]

    if case.description:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Descripción:*\n{case.description}"},
            }
        )
        blocks.append({"type": "divider"})

    available_actions = _ACTIONS_BY_STATUS.get(case.status, [])

    if case.channel:
        blocks.append(
            {
                "type": "input",
                "block_id": "comment_block",
                "optional": True,
                "label": {"type": "plain_text", "text": "Agregar comentario al canal (opcional)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "comment_input",
                    "multiline": True,
                },
            }
        )

    if not available_actions and not case.channel:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "_No hay acciones disponibles para este caso en su estado actual._",
                    }
                ],
            }
        )

    if available_actions:
        blocks.append(
            {
                "type": "input",
                "block_id": "action_block",
                "label": {"type": "plain_text", "text": "¿Qué querés hacer con este caso?"},
                "element": {
                    "type": "radio_buttons",
                    "action_id": "selected_action",
                    "options": [
                        {"text": {"type": "plain_text", "text": label}, "value": value}
                        for value, label in available_actions
                    ],
                },
            }
        )

        if any(value == "derive_to_internal_team" for value, _ in available_actions):
            blocks.append(
                {
                    "type": "input",
                    "block_id": "team_block",
                    "optional": True,
                    "label": {
                        "type": "plain_text",
                        "text": 'Equipo interno (solo si elegiste "Derivar")',
                    },
                    "element": {
                        "type": "static_select",
                        "action_id": "selected_team",
                        "options": [
                            {"text": {"type": "plain_text", "text": team}, "value": team}
                            for team in _TEAM_OPTIONS
                        ],
                    },
                }
            )

    view: dict = {
        "type": "modal",
        "callback_id": CALLBACK_ID,
        "private_metadata": case.id,
        "title": {"type": "plain_text", "text": "Detalle del caso"},
        "close": {"type": "plain_text", "text": "Cerrar"},
        "blocks": blocks,
    }

    if available_actions or case.channel:
        view["submit"] = {"type": "plain_text", "text": "Confirmar"}

    return view