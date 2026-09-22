"""
Constructores de Block Kit para el detalle de un caso.

El modal principal (build_case_detail_modal) enruta a distintas
"pantallas" según el estado del caso — nunca se cierra entre pasos,
se va reemplazando con views.update:

- Assigned to Branch → pantalla de "Iniciar" (un solo botón, sin campos).
- In Progress → pantalla de elección (Cerrar Caso / Derivar Caso, sin
  campos). Clickear cualquiera de las dos abre su propia sub-pantalla
  CON campos — y como Slack exige que todo modal con bloques `input`
  tenga un `submit`, esas dos sub-pantallas usan el submit real del
  modal (con su propio callback_id) en vez de un botón suelto.
- Escalated Internal / resto de estados → comportamiento previo, sin
  cambios en esta vuelta (queda para la próxima ronda de ajustes).

Además:
- build_team_select_modal: modal secundario (views.push) para derivar
  un caso desde el equipo interno a otro equipo.
- build_message_modal: modal chico de confirmación/error.
"""

from domain.case import Case, CaseStatus

CALLBACK_ID = "case_detail_modal"
TEAM_SELECT_CALLBACK_ID = "team_select_modal"
CLOSE_CASE_CALLBACK_ID = "close_case_modal"
DERIVE_CASE_CALLBACK_ID = "derive_case_modal"

# Equipos internos disponibles para derivar (tal cual se cargaron en el
# picklist Internal_Team__c de Salesforce).
_TEAM_OPTIONS = ["Legales", "Logistica", "Marketing", "Cobros"]

# Botones de acción para el equipo interno y los estados terminales.
# OJO: el caso de un equipo interno queda en Status "New" (a pedido del
# cliente — ver domain/case.py), por eso las acciones del equipo interno
# están acá, no en un estado "escalated". ESCALATED_INTERNAL ya no se usa
# activamente, queda vacío por compatibilidad con casos viejos.
_ACTION_BUTTONS_BY_STATUS: dict[CaseStatus, list[tuple[str, str, str | None]]] = {
    CaseStatus.NEW: [
        ("derive_to_internal_team", "🔺 Derivar a equipo interno", None),
        ("finish_internal_work", "↩️ Devolver a Sucursal", "primary"),
    ],
    CaseStatus.ESCALATED_INTERNAL: [],
    CaseStatus.RETURNED_TO_CALL_CENTER: [],
    CaseStatus.CLOSED: [],
}


def _info_blocks(case: Case) -> list[dict]:
    """Bloques de info del caso, compartidos por todas las pantallas."""
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
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Descripción:*\n{case.description}"}}
        )
        blocks.append({"type": "divider"})
    return blocks


def _base_view(
    case_id: str, blocks: list[dict], submit_label: str | None = None, callback_id: str = CALLBACK_ID
) -> dict:
    view: dict = {
        "type": "modal",
        "callback_id": callback_id,
        "private_metadata": case_id,
        "title": {"type": "plain_text", "text": "Detalle del caso"},
        "close": {"type": "plain_text", "text": "Cerrar"},
        "blocks": blocks,
    }
    if submit_label:
        view["submit"] = {"type": "plain_text", "text": submit_label}
    return view


def _error_block(message: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": f":warning: {message}"}}


def build_case_detail_modal(case: Case) -> dict:
    """Punto de entrada: enruta a la pantalla que corresponde según el estado del caso."""
    if case.status == CaseStatus.ASSIGNED_TO_BRANCH:
        return build_start_screen(case)
    if case.status == CaseStatus.IN_PROGRESS:
        return build_in_progress_choice_screen(case)
    return _build_generic_modal(case)


def build_start_screen(case: Case) -> dict:
    """Pantalla 1: caso recién asignado a la sucursal — un solo botón, "Iniciar". Sin campos, sin submit."""
    blocks = _info_blocks(case)
    blocks.append(
        {
            "type": "actions",
            "block_id": "start_actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": "start_progress",
                    "text": {"type": "plain_text", "text": "▶️ Iniciar", "emoji": True},
                    "style": "primary",
                }
            ],
        }
    )
    return _base_view(case.id, blocks)


def build_in_progress_choice_screen(case: Case) -> dict:
    """Pantalla 2: caso en progreso — elegir Cerrar o Derivar. Sin campos, sin submit."""
    blocks = _info_blocks(case)
    blocks.append(
        {
            "type": "actions",
            "block_id": "in_progress_actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": "show_close_case_form",
                    "text": {"type": "plain_text", "text": "✅ Cerrar Caso", "emoji": True},
                },
                {
                    "type": "button",
                    "action_id": "show_derive_case_form",
                    "text": {"type": "plain_text", "text": "🔺 Derivar Caso", "emoji": True},
                    "style": "primary",
                },
            ],
        }
    )
    return _base_view(case.id, blocks)


def build_close_case_form(case: Case, error: str | None = None) -> dict:
    """
    Pantalla 3a: cerrar el caso — comentario opcional + submit real del
    modal (callback_id propio, CLOSE_CASE_CALLBACK_ID), porque tiene un
    bloque `input` y Slack exige un submit para eso.
    """
    blocks = _info_blocks(case)
    if error:
        blocks.append(_error_block(error))
    blocks.append(
        {
            "type": "input",
            "block_id": "close_comment_block",
            "optional": True,
            "label": {"type": "plain_text", "text": "Comentario de cierre (opcional)"},
            "element": {"type": "plain_text_input", "action_id": "close_comment_input", "multiline": True},
        }
    )
    blocks.append(
        {
            "type": "actions",
            "block_id": "close_case_actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": "back_to_choice",
                    "text": {"type": "plain_text", "text": "‹ Volver", "emoji": True},
                }
            ],
        }
    )
    return _base_view(case.id, blocks, submit_label="✅ Confirmar cierre", callback_id=CLOSE_CASE_CALLBACK_ID)


def build_derive_case_form(case: Case, error: str | None = None) -> dict:
    """
    Pantalla 3b: derivar a un equipo interno — comentario opcional +
    equipo (obligatorio, Slack lo valida solo por no tener "optional")
    + submit real del modal (callback_id propio, DERIVE_CASE_CALLBACK_ID).
    """
    blocks = _info_blocks(case)
    if error:
        blocks.append(_error_block(error))
    blocks.append(
        {
            "type": "input",
            "block_id": "derive_comment_block",
            "optional": True,
            "label": {"type": "plain_text", "text": "Comentario (opcional)"},
            "element": {"type": "plain_text_input", "action_id": "derive_comment_input", "multiline": True},
        }
    )
    blocks.append(
        {
            "type": "input",
            "block_id": "derive_team_block",
            "label": {"type": "plain_text", "text": "Equipo interno"},
            "element": {
                "type": "static_select",
                "action_id": "selected_team",
                "placeholder": {"type": "plain_text", "text": "Buscar equipo..."},
                "options": [
                    {"text": {"type": "plain_text", "text": team}, "value": team} for team in _TEAM_OPTIONS
                ],
            },
        }
    )
    blocks.append(
        {
            "type": "actions",
            "block_id": "derive_case_actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": "back_to_choice",
                    "text": {"type": "plain_text", "text": "‹ Volver", "emoji": True},
                }
            ],
        }
    )
    return _base_view(
        case.id, blocks, submit_label="🔺 Confirmar derivación", callback_id=DERIVE_CASE_CALLBACK_ID
    )


def _build_generic_modal(case: Case) -> dict:
    """Comportamiento previo, sin cambios: equipo interno y estados terminales."""
    blocks = _info_blocks(case)

    if case.channel:
        blocks.append(
            {
                "type": "input",
                "block_id": "comment_block",
                "optional": True,
                "label": {"type": "plain_text", "text": "Agregar comentario al canal (opcional)"},
                "element": {"type": "plain_text_input", "action_id": "comment_input", "multiline": True},
            }
        )
        blocks.append({"type": "divider"})

    action_buttons = _ACTION_BUTTONS_BY_STATUS.get(case.status, [])

    if action_buttons:
        elements = []
        for action_id, label, style in action_buttons:
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

    submit_label = "Guardar comentario" if case.channel else None
    return _base_view(case.id, blocks, submit_label)


def build_team_select_modal(case_id: str) -> dict:
    """Modal chico (views.push) para elegir a qué equipo interno derivar un caso, desde otro equipo."""
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