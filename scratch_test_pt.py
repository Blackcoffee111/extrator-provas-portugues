def _build_pt_grouped_html(
    paired: list,
) -> str:
    """Renderiza questões PT agrupadas por GRUPO e PARTE.

    context_stem cards aparecem no topo de cada grupo/parte.
    Questões regulares nunca mostram enunciado_contexto_pai (está no stem acima).
    """
    _GRUPO_ORDER = {"I": 0, "II": 1, "III": 2, "IV": 3, "V": 4}
    
    # Todos os grupos presentes, ordenados
    all_grupos = sorted(
        {q.grupo for q, _ in paired if q.grupo},
        key=lambda g: _GRUPO_ORDER.get(g, 9),
    )

    html_parts = []
    idx = 0
    for grupo in all_grupos:
        html_parts.append(f'<div class="grupo-section" data-grupo="{grupo}">')
        html_parts.append(f'<div class="grupo-header">Grupo {grupo}</div>')

        grupo_items = [(q, ov) for q, ov in paired if q.grupo == grupo]
        current_parte = None

        for q, ov in grupo_items:
            if q.tipo_item == "context_stem":
                parts = q.id_item.split("-")
                parte = parts[1] if len(parts) >= 3 and parts[1] in ("A", "B", "C") else ""
            else:
                parts = str(q.id_item).split("-")
                parte = parts[1] if len(parts) >= 3 and parts[1] in ("A", "B", "C") else None

            # Only open a new parte-section if we hit a context_stem or question with an EXPLICIT parte like "A"
            if parte is not None and parte != "" and parte != current_parte:
                if current_parte is not None:
                    html_parts.append("</div>")  # Close previous parte
                current_parte = parte
                html_parts.append(f'<div class="parte-section" data-parte="{parte}">')
                html_parts.append(f'<div class="parte-header">Parte {parte}</div>')

            idx += 1
            html_parts.append(f"<!-- Render q.id_item {q.id_item} idx={idx} -->")

        if current_parte is not None:
            html_parts.append("</div>")  # Close the final parte

        html_parts.append("</div>")

    # Questões sem grupo (provas antigas ou não-PT): renderização linear
    for q, ov in paired:
        if not q.grupo:
            idx += 1
            html_parts.append(f"<!-- Render no-group {q.id_item} idx={idx} -->")

    return "\n".join(html_parts)
