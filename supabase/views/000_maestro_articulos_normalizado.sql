-- Vista normalizada del maestro de artículos.
-- No modifica la tabla de origen. Conserva la descripción original y separa
-- color y talle cuando existen los marcadores correspondientes. Ambos son
-- opcionales y pueden aparecer en cualquier orden.

create or replace view public.vw_maestro_articulos_normalizado
with (security_invoker = true)
as
select
  m.id_articulo,
  m.sku,
  m.descripcion as descripcion_original,
  m.grupo_articulo,
  m.rubro,
  m.subrubro,
  case
    when m.descripcion like '% C:%'
      then nullif(
        btrim(
          split_part(
            split_part(m.descripcion, ' C:', 2),
            ' T:',
            1
          )
        ),
        ''
      )
    else null
  end as color,
  case
    when m.descripcion like '% T:%'
      then nullif(
        btrim(
          split_part(
            split_part(m.descripcion, ' T:', 2),
            ' C:',
            1
          )
        ),
        ''
      )
    else null
  end as talle,
  case
    when m.descripcion is null or btrim(m.descripcion) = '' then 'sin_descripcion'
    when m.descripcion like '% C:%'
      and m.descripcion like '% T:%' then 'con_color_y_talle'
    when m.descripcion like '% C:%' then 'solo_color'
    when m.descripcion like '% T:%' then 'solo_talle'
    else 'sin_variantes_declaradas'
  end as estado_parseo_variante,
  m.updated_at
from centum_sync.maestro_articulos m;

comment on view public.vw_maestro_articulos_normalizado is
  'Maestro de Centum enriquecido con color y talle opcionales extraídos de la descripción, conservando el texto original y una clasificación descriptiva.';

