"""
Constructores de Block Kit para el detalle de un caso.

Dos vistas:
- build_case_detail_modal: el modal principal, con la info del caso,
  el campo de comentario, y botones de acción independientes (no radio
  buttons) — cada botón dispara su acción al toque de un clic.
- build_team_select_modal: modal secundario, se abre encima del
  principal (views.push) cuando se clickea "Derivar a equipo interno",
  para elegir a qué equipo.
- build_message_modal: modal chico de confirmación/error, se usa para
  reemplazar al principal después de ejecutar una acción.

Las acciones disponibles por estado son una copia deliberada a nivel de
presentación de las transiciones válidas en domain/case.py — si se
desincroniza, lo peor que pasa es que domain.Case rechace la acción al
guardar (ver application/case_service.py).
"""

from domain.case import Case, CaseStatus

CALLBACK_ID = "case_detail_modal"
TEAM_SELECT_CALLBACK_ID = "team_select_modal"

# Equipos internos disponibles para derivar (tal cual se cargaron en el
# picklist Internal_Team__c de Salesforce).
_TEAM_OPTIONS = ["Legales", "Logistica", "Marketing", "Cobros"]

# Botones de acción por estado: (action_id, label, style).
# style: "primary" (verde), "danger" (rojo), o None (gris, default).
_ACTION_BUTTONS_BY_STATUS: dict[CaseStatus, list[tuple[str, str, str | None]]] = {
    CaseStatus.NEW: [],
    CaseStatus.ASSIGNED_TO_BRANCH: [
        ("derive_to_internal_team", "🔺 Derivar a equipo interno", "primary"),
        ("return_to_call_center", "↩️ Devolver a Call Center", None),
        ("close_case", "✅ Cerrar caso", None),
    ],
    CaseStatus.IN_PROGRESS: [
        ("derive_to_internal_team", "🔺 Derivar a equipo interno", "primary"),
        ("return_to_call_center", "↩️ Devolver a Call Center", None),
        ("close_case", "✅ Cerrar caso", None),
    ],
    CaseStatus.ESCALATED_INTERNAL: [
        ("derive_to_internal_team", "🔺 Derivar a equipo interno", None),
        ("finish_internal_work", "↩️ Devolver a Sucursal", "primary"),
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
        blocks.append({"type": "divider"})

    action_buttons = _ACTION_BUTTONS_BY_STATUS.get(case.status, [])

    if action_buttons:
        elements = []
        for action_id, label, style in action_buttons:
            # Para el equipo interno, el botón de finalizar menciona el
            # equipo puntual (Legales/Cobros/Logística).
            if action_id == "finish_internal_work" and case.assigned_team:
                label = f"↩️ Devolver a Sucursal ({case.assigned_team})"
            button: dict = {
                "type": "button",
                "action_id": action_id,
                "text": {"type": "plain_text", "text": label, "emoji": True},
            }
            if style:
                button["style"] = style
            elements.append(button)
        blocks.append({"type": "actions", "block_id": "case_actions", "elements": elements})
    elif not case.channel:
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

    view: dict = {
        "type": "modal",
        "callback_id": CALLBACK_ID,
        "private_metadata": case.id,
        "title": {"type": "plain_text", "text": "Detalle del caso"},
        "close": {"type": "plain_text", "text": "Cerrar"},
        "blocks": blocks,
    }

    # El submit de este modal sirve UNICAMENTE para guardar el comentario
    # (las acciones de estado van por los botones de arriba, no por acá).
    if case.channel:
        view["submit"] = {"type": "plain_text", "text": "Guardar comentario"}

    return view


def build_team_select_modal(case_id: str) -> dict:
    """Modal chico para elegir a qué equipo interno derivar un caso."""
    return {
        "type": "modal",
        "callback_id": TEAM_SELECT_CALLBACK_ID,
        "private_metadata": case_id,
        "title": {"type": "plain_text", "text": "Derivar caso"},
        "submit": {"type": "plain_text", "text": "Derivar"},
        "close": {"type": "plain_text", "text": "Cancelar"},
        "blocks": [
            {
                "type": "input",
                "block_id": "team_block",
                "label": {"type": "plain_text", "text": "Elegí el equipo interno"},
                "element": {
                    "type": "static_select",
                    "action_id": "selected_team",
                    "options": [
                        {"text": {"type": "plain_text", "text": team}, "value": team}
                        for team in _TEAM_OPTIONS
                    ],
                },
            }
        ],
    }


def build_message_modal(text: str) -> dict:
    """Modal chico de confirmación o error, para reemplazar al principal tras una acción."""
    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": "Listo"},
        "close": {"type": "plain_text", "text": "Cerrar"},
        "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": text}}],
    }