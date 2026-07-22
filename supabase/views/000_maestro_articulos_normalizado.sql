-- Vista normalizada del maestro de artículos.
-- No modifica la tabla de origen. Conserva la descripción original y separa
-- color y talle cuando respeta el patrón "... C:<color> T:<talle>".

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
    when m.descripcion like '% C:% T:%'
      then nullif(
        btrim(split_part(split_part(m.descripcion, ' C:', 2), ' T:', 1)),
        ''
      )
    else null
  end as color,
  case
    when m.descripcion like '% C:% T:%'
      then nullif(btrim(split_part(m.descripcion, ' T:', 2)), '')
    else null
  end as talle,
  case
    when m.descripcion is null or btrim(m.descripcion) = '' then 'sin_descripcion'
    when m.descripcion not like '% C:%' then 'sin_color'
    when m.descripcion not like '% T:%' then 'sin_talle'
    when nullif(
      btrim(split_part(split_part(m.descripcion, ' C:', 2), ' T:', 1)),
      ''
    ) is null then 'color_vacio'
    when nullif(btrim(split_part(m.descripcion, ' T:', 2)), '') is null
      then 'talle_vacio'
    else 'ok'
  end as estado_parseo_variante,
  m.updated_at
from centum_sync.maestro_articulos m;

comment on view public.vw_maestro_articulos_normalizado is
  'Maestro de Centum enriquecido con color y talle extraídos de la descripción, conservando el texto original y el estado del parseo.';

