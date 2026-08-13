# packs/ — lo que es tuyo, no del plugin

Un plugin de este marketplace tiene dos capas, y la distinción no es cosmética:

| Capa | Qué vive ahí | ¿Sirve para cualquiera? |
|---|---|---|
| **core** (`lib/`, `mcp/`, `skills/`, `commands/`) | cómo hablarle al servicio: auth, ritmo, endpoints, tools | **sí** |
| **pack** (`packs/<proyecto>/`) | ids de tus herramientas, presets, prompts, nombres de tu proyecto | **no**, es tuyo |

La regla: **si otra persona no puede usarlo tal cual, es un pack.**

Un `appletId`, un `space_version_id`, un `project_id`, la lista de facciones de
tu juego, tus presets de estilo — nada de eso va en el core. Si se cuela, el
plugin deja de ser instalable por otro y encima queda con identificadores tuyos
en un repo público.

## Estructura de un pack

```
packs/
└── mi-proyecto/
    ├── pack.json          ids y config del proyecto
    ├── recipes/           presets ejecutables
    └── notas.md           catálogo de tus herramientas, decisiones, lo que sea
```

`pack.json` mínimo:

```json
{
  "name": "mi-proyecto",
  "description": "Para qué es este pack",
  "ids": {
    "appletId": "…",
    "projectId": "…"
  },
  "defaults": {
    "style": "…"
  }
}
```

## Cómo se elige un pack

Por variable de entorno o por argumento de la tool — nunca hardcodeado:

```bash
export EXAMPLE_PACK=mi-proyecto
```

En el código, resolvelo así (y que falle con un mensaje claro si no existe):

```python
def load_pack(name: str | None = None) -> dict:
    name = name or os.environ.get(f"{SERVICE.upper()}_PACK")
    if not name:
        return {}                      # sin pack: el core funciona igual
    p = Path(__file__).resolve().parents[1] / "packs" / name / "pack.json"
    if not p.is_file():
        avail = [d.name for d in p.parents[0].parent.iterdir() if d.is_dir()]
        raise ServiceError(f"No existe el pack {name!r}. Disponibles: {avail}")
    return json.loads(p.read_text())
```

**El core tiene que funcionar sin ningún pack.** Un pack agrega atajos, no
capacidades: si una tool sólo anda con pack, esa tool está mal diseñada.

## Publicar packs, o no

Un pack en el repo público es legible por cualquiera. Si tiene ids de proyectos
privados o prompts que no querés compartir, dejalo fuera: los packs también se
leen desde `~/.config/<plugin>/packs/`, que nunca entra al repo.

Ningún pack lleva credenciales. Nunca. Eso va en `~/.config/<plugin>/`.
