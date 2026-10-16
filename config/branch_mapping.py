"""
Mapeo temporal Slack User ID -> Sucursal (branch), para la demo.

En un entorno real esto viviría en Salesforce (ej. un campo en el User)
o en una base de datos propia. Para esta demo, alcanza con un diccionario
fijo que completás a mano con los usuarios de tu workspace de prueba.

Cómo conseguir el Slack User ID de alguien:
en Slack, clic en su perfil -> los tres puntos ("More") -> "Copy member ID".
Empieza con "U", ej. "U0123ABCDEF".
"""

SLACK_USER_TO_BRANCH: dict[str, str] = {
    # "U0123ABCDEF": "Sucursal Centro",
    # "U0456GHIJKL": "Sucursal Norte",
}

# Usuarios que ven TODOS los casos de la demo, sin filtrar por sucursal.
SUPERUSER_SLACK_IDS: set[str] = {
    # "U0123ABCDEF",
}

# Usuarios que ven los casos derivados a un equipo interno puntual
# (Legales, Logistica, Marketing, Cobros), sin importar la sucursal.
SLACK_USER_TO_TEAM: dict[str, str] = {
    # "U0789MNBVC": "Cobros",
}


def get_branch_for_user(slack_user_id: str) -> str | None:
    """Devuelve la sucursal asociada a un usuario de Slack, o None si no está mapeado."""
    return SLACK_USER_TO_BRANCH.get(slack_user_id)


def is_superuser(slack_user_id: str) -> bool:
    """True si el usuario debe ver todos los casos, sin filtrar por sucursal."""
    return slack_user_id in SUPERUSER_SLACK_IDS


def get_team_for_user(slack_user_id: str) -> str | None:
    """Devuelve el equipo interno que sigue este usuario (todas las sucursales), o None si no aplica."""
    return SLACK_USER_TO_TEAM.get(slack_user_id)
