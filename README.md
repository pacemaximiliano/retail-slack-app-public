# Retail Slack ↔ Salesforce App

App de Slack (Bolt, modo HTTP) para que las sucursales de Retail gestionen
casos derivados desde Salesforce Service Cloud (Call Center), y viceversa.

## Arquitectura

- `domain/` — Entidades y reglas de negocio puras (sin dependencias externas).
- `application/` — Casos de uso que orquestan domain + infrastructure. (pendiente)
- `infrastructure/` — Clientes concretos de Slack y Salesforce. (pendiente)
- `views/` — Builders de Block Kit para App Home y modals. (pendiente)
- `config/` — Configuración vía pydantic-settings, leyendo `.env`.

## Setup local

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# completar .env con las credenciales reales de Slack y Salesforce
```

## Estado actual

- [x] Configuración base (`config/settings.py`)
- [x] Modelo de dominio `Case` con máquina de estados (`domain/case.py`)
- [ ] Cliente de Salesforce (OAuth Client Credentials Flow)
- [ ] App Home con listado de casos
- [ ] Modals de detalle / derivación
- [ ] Deploy a Render
